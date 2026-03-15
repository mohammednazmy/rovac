package com.rovac.phonesensors;

import android.Manifest;
import android.app.*;
import android.content.*;
import androidx.lifecycle.LifecycleService;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.location.LocationRequest;
import android.os.*;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayOutputStream;
import androidx.core.app.NotificationCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.ContextCompat;

import java.util.concurrent.Executor;

/**
 * Foreground service that owns the rosbridge WebSocket session, IMU sensors,
 * GPS, and camera. Keeps publishing when the screen is off.
 */
public class SensorService extends LifecycleService implements SensorEventListener {

    private static final String TAG = "SensorService";
    private static final String CHANNEL_ID = "rovac_sensor";
    private static final int NOTIF_ID = 1;
    public static final String ACTION_STOP = "com.rovac.phonesensors.STOP";
    public static final String ACTION_BOOT_START = "com.rovac.phonesensors.BOOT_START";
    private static final String PREFS = "rovac_settings";

    /* ── State ─────────────────────────────────────────────── */
    private XrceBridge bridge;
    private SensorManager sensorMgr;
    private LocationManager locationMgr;
    private Camera2JpegCapture camera;
    private MjpegServer mjpegServer;

    /* Sensor references — compare by reference, NOT by type constant
     * (Samsung uses vendor-specific type IDs for rotation vector) */
    private Sensor accelSensor, gyroSensor, rotSensor;

    private HandlerThread pubThread;
    private HandlerThread sensorThread;
    private Handler pubHandler;

    private volatile float[] latestAccel = new float[3];
    private volatile float[] latestGyro  = new float[3];
    private volatile float[] latestQuat  = {0,0,0,1}; /* x,y,z,w */
    private boolean cameraEnabled = false;

    private boolean running = false;
    private long imuCount = 0;
    private int pingFailCount = 0;
    private static final int PING_FAIL_THRESHOLD = 2;

    /* GPS — store latest, publish from pub thread to avoid cross-thread mutex contention */
    private volatile double[] latestGps = null; /* lat, lon, alt */
    private volatile byte[] latestJpeg = null; /* camera frame for pub thread to send */
    private volatile long latestJpegTs = 0;

    private final LocationListener gpsListener = new LocationListener() {
        @Override
        public void onLocationChanged(@NonNull Location loc) {
            if (!running) return;
            latestGps = new double[]{loc.getLatitude(), loc.getLongitude(), loc.getAltitude(),
                                     (double)loc.getTime()};
            if (statusListener != null)
                statusListener.onGpsUpdate(loc.getLatitude(), loc.getLongitude(), loc.getAltitude());
        }

        @Override public void onProviderEnabled(@NonNull String p) {
            Log.i(TAG, "Location provider enabled: " + p);
        }
        @Override public void onProviderDisabled(@NonNull String p) {
            Log.w(TAG, "Location provider disabled: " + p);
        }
    };

    /* Status listener for UI updates */
    public interface StatusListener {
        void onStatus(String msg);
        void onImuUpdate(long count, float[] acc, float[] gyro, float[] quat);
        void onGpsUpdate(double lat, double lon, double alt);
        void onCameraFrame(int bytes, int httpClients);
    }
    private StatusListener statusListener;
    public void setStatusListener(StatusListener l) { this.statusListener = l; }

    private android.view.Surface previewSurfaceRef;

    /** No-op — legacy */
    public void setPreviewSurface(android.view.Surface surface) {
        previewSurfaceRef = surface;
    }

    /** Set PreviewView for live camera feed on phone screen */
    public void setPreviewView(androidx.camera.view.PreviewView view) {
        if (camera != null) camera.setPreviewView(view);
        this.previewViewRef = view;
    }
    private androidx.camera.view.PreviewView previewViewRef;

    /** Toggle flashlight */
    public void toggleTorch() {
        if (camera != null) camera.toggleTorch();
    }
    public boolean isTorchOn() {
        return camera != null && camera.isTorchEnabled();
    }

    /* Binder for Activity */
    private final IBinder binder = new LocalBinder();
    public class LocalBinder extends Binder {
        SensorService getService() { return SensorService.this; }
    }
    @Nullable @Override public IBinder onBind(Intent i) { super.onBind(i); return binder; }

    /* ── Lifecycle ─────────────────────────────────────────── */

    @Override
    public void onCreate() {
        super.onCreate();
        createNotifChannel();
        bridge = new XrceBridge();
        sensorMgr = (SensorManager) getSystemService(SENSOR_SERVICE);
        locationMgr = (LocationManager) getSystemService(LOCATION_SERVICE);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        super.onStartCommand(intent, flags, startId);
        String action = (intent != null) ? intent.getAction() : null;
        Log.i(TAG, "onStartCommand: action=" + action);

        if (ACTION_STOP.equals(action)) {
            stopSensor();
            return START_NOT_STICKY;
        }

        if (ACTION_BOOT_START.equals(action) && !running) {
            SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
            String ip   = p.getString("agent_ip", "192.168.1.200");
            String port = p.getString("agent_port", "9090");
            int domain  = p.getInt("domain_id", 42);
            boolean cam = p.getBoolean("camera_enabled", false);
            Log.i(TAG, "Boot auto-start → " + ip + ":" + port + " camera=" + cam);
            startSensor(ip, port, domain, cam);
        }

        /* Bare intents (from startForegroundService) — do nothing.
         * The Activity calls startSensor() directly via the binder. */
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        stopSensor();
        super.onDestroy();
    }

    public boolean isRunning() { return running; }

    /* ── Start / Stop ──────────────────────────────────────── */

    private volatile boolean starting = false; /* guard against concurrent startSensor calls */

    public void startSensor(String ip, String port, int domain, boolean withCamera) {
        if (running || starting) {
            Log.i(TAG, "Already running/starting, ignoring startSensor");
            return;
        }
        starting = true;
        cameraEnabled = withCamera;
        Log.i(TAG, "startSensor: ip=" + ip + " port=" + port + " camera=" + withCamera);

        promoteToForeground();

        pubThread = new HandlerThread("rosbridge-pub");
        pubThread.start();
        pubHandler = new Handler(pubThread.getLooper());

        pubHandler.post(() -> {
            postStatus("Connecting to " + ip + ":" + port + " ...");

            if (!bridge.connect(ip, port, domain)) {
                postStatus("Connection FAILED");
                starting = false;
                return;
            }
            if (!bridge.createPublishers(cameraEnabled)) {
                postStatus("Entity creation FAILED");
                bridge.disconnect();
                starting = false;
                return;
            }

            running = true;
            starting = false;
            postStatus("CONNECTED — publishing");
            updateNotif("Publishing IMU" + (cameraEnabled ? " + Camera" : "") + " + GPS");

            /* Register IMU sensors directly on pub thread — callbacks fire here too.
             * This is the pattern that was verified working earlier. */
            accelSensor = sensorMgr.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
            gyroSensor  = sensorMgr.getDefaultSensor(Sensor.TYPE_GYROSCOPE);
            rotSensor   = sensorMgr.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);
            /* Register sensors on a DEDICATED sensor thread — NOT on pubHandler
             * (pubHandler's 50Hz timer starves sensor event delivery if shared) */
            sensorThread = new HandlerThread("sensor-recv");
            sensorThread.start();
            Handler sensorHandler = new Handler(sensorThread.getLooper());
            if (accelSensor != null) {
                boolean ok = sensorMgr.registerListener(SensorService.this, accelSensor,
                        SensorManager.SENSOR_DELAY_GAME, sensorHandler);
                Log.i(TAG, "Accelerometer registered=" + ok + " (type=" + accelSensor.getType() + ")");
            }
            if (gyroSensor != null) {
                boolean ok = sensorMgr.registerListener(SensorService.this, gyroSensor,
                        SensorManager.SENSOR_DELAY_GAME, sensorHandler);
                Log.i(TAG, "Gyroscope registered=" + ok + " (type=" + gyroSensor.getType() + ")");
            }
            if (rotSensor != null) {
                boolean ok = sensorMgr.registerListener(SensorService.this, rotSensor,
                        SensorManager.SENSOR_DELAY_GAME, sensorHandler);
                Log.i(TAG, "Game rotation vector registered=" + ok + " (type=" + rotSensor.getType() + ")");
            }

            /* GPS — register on main Looper with explicit Looper param */
            startGps();

            /* Camera */
            if (cameraEnabled && ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                    == PackageManager.PERMISSION_GRANTED) {
                camera = new Camera2JpegCapture(SensorService.this);
                if (previewViewRef != null) camera.setPreviewView(previewViewRef);
                /* Start MJPEG HTTP server for high-quality streaming */
                mjpegServer = new MjpegServer();
                mjpegServer.setTorchCallback(on -> {
                    if (camera != null) camera.setTorch(on);
                });
                mjpegServer.start();
                Log.i(TAG, "MJPEG server on port " + MjpegServer.PORT);

                camera.setCallback((jpeg, w, h, ts) -> {
                    /* Full-res JPEG → MJPEG HTTP server (no MTU limit) */
                    if (mjpegServer != null) mjpegServer.pushFrame(jpeg);

                    /* Downscaled JPEG → rosbridge (low-res for ROS2 topic) */
                    byte[] small = recompressJpeg(jpeg, 240, 180, 30);
                    if (small != null) {
                        latestJpeg = small;
                        latestJpegTs = ts;
                    }

                    if (statusListener != null) {
                        int clients = mjpegServer != null ? mjpegServer.getClientCount() : 0;
                        statusListener.onCameraFrame(jpeg.length, clients);
                    }
                });
                camera.open();
            }

            /* Start IMU publish loop (50 Hz) on pub thread */
            Log.i(TAG, "Starting IMU publish loop");
            scheduleImuPublish();

            /* Start health check (every 5s) */
            scheduleHealthCheck();
        });
    }

    @SuppressWarnings("MissingPermission")
    private void startGps() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "Location permission not granted");
            return;
        }

        Handler mainH = new Handler(Looper.getMainLooper());
        mainH.post(() -> {
            try {
                /* Use GPS provider */
                if (locationMgr.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                    locationMgr.requestLocationUpdates(
                            LocationManager.GPS_PROVIDER, 1000, 0,
                            gpsListener, Looper.getMainLooper());
                    Log.i(TAG, "GPS provider registered");
                } else {
                    Log.w(TAG, "GPS provider not enabled");
                }
            } catch (Exception e) {
                Log.w(TAG, "GPS provider failed: " + e.getMessage());
            }

            try {
                /* Also use network provider as fallback */
                if (locationMgr.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                    locationMgr.requestLocationUpdates(
                            LocationManager.NETWORK_PROVIDER, 2000, 0,
                            gpsListener, Looper.getMainLooper());
                    Log.i(TAG, "Network location provider registered");
                } else {
                    Log.w(TAG, "Network provider not enabled");
                }
            } catch (Exception e) {
                Log.w(TAG, "Network provider failed: " + e.getMessage());
            }

            /* Publish last known location immediately */
            try {
                Location last = locationMgr.getLastKnownLocation(LocationManager.GPS_PROVIDER);
                if (last == null) last = locationMgr.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
                if (last != null) {
                    Log.i(TAG, "Last known location: " + last.getLatitude() + ", " + last.getLongitude());
                    latestGps = new double[]{last.getLatitude(), last.getLongitude(),
                                             last.getAltitude(), (double)last.getTime()};
                } else {
                    Log.i(TAG, "No last known location available");
                }
            } catch (Exception e) {
                Log.w(TAG, "Last known location failed: " + e.getMessage());
            }
        });
    }

    public void stopSensor() {
        running = false;
        starting = false;
        sensorMgr.unregisterListener(this);
        locationMgr.removeUpdates(gpsListener);
        if (sensorThread != null) { sensorThread.quitSafely(); sensorThread = null; }
        if (mjpegServer != null) { mjpegServer.stop(); mjpegServer = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (pubHandler != null) {
            pubHandler.post(() -> {
                bridge.disconnect();
                pubThread.quitSafely();
            });
        }
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
        postStatus("Disconnected");
    }

    /* ── IMU publish loop (50 Hz) ──────────────────────────── */

    private void scheduleImuPublish() {
        if (!running || pubHandler == null) return;
        pubHandler.postDelayed(() -> {
            if (!running) return;
            try {
                long now = System.currentTimeMillis();
                int sec = (int)(now / 1000);
                int nsec = (int)((now % 1000) * 1_000_000);
                float[] q = latestQuat, g = latestGyro, a = latestAccel;

                bridge.publishImu(sec, nsec, "phone_imu",
                        q[0], q[1], q[2], q[3],
                        g[0], g[1], g[2],
                        a[0], a[1], a[2]);

                /* Publish GPS (every 50th tick = ~1Hz) */
                imuCount++;
                if (imuCount % 50 == 0) {
                    double[] gps = latestGps;
                    if (gps != null) {
                        int gsec = (int)((long)gps[3] / 1000);
                        int gnsec = (int)(((long)gps[3] % 1000) * 1_000_000);
                        bridge.publishNavSatFix(gsec, gnsec, "phone_gps",
                                0, 1, gps[0], gps[1], gps[2], 0);
                    }
                }

                /* Publish camera JPEG (every 25th tick = ~2Hz) */
                if (imuCount % 25 == 0) {
                    byte[] jpeg = latestJpeg;
                    long jpegTs = latestJpegTs;
                    if (jpeg != null) {
                        latestJpeg = null; /* consume */
                        int csec = (int)(jpegTs / 1000);
                        int cnsec = (int)((jpegTs % 1000) * 1_000_000);
                        bridge.publishCompressedImage(csec, cnsec, "phone_camera", "jpeg", jpeg);
                    }
                }
                if (imuCount % 500 == 0) {
                    Log.i(TAG, "IMU #" + imuCount + " acc=" +
                        String.format("%.2f,%.2f,%.2f", a[0], a[1], a[2]));
                }
                /* Update UI at ~5Hz (every 10th publish at 50Hz) */
                if (imuCount % 10 == 0 && statusListener != null) {
                    statusListener.onImuUpdate(imuCount, a, g, q);
                }
            } catch (Exception e) {
                Log.e(TAG, "IMU publish error", e);
            }
            scheduleImuPublish();
        }, 20);
    }

    /* ── Health check + reconnect (every 5s) ───────────────── */

    private void scheduleHealthCheck() {
        if (!running || pubHandler == null) return;
        pubHandler.postDelayed(() -> {
            if (!running) return;
            boolean ok = bridge.ping(1000);
            if (ok) {
                pingFailCount = 0;
            } else {
                pingFailCount++;
                Log.w(TAG, "Ping failed (" + pingFailCount + "/" + PING_FAIL_THRESHOLD + ")");
                if (pingFailCount >= PING_FAIL_THRESHOLD) {
                    postStatus("Agent lost — reconnecting...");
                    updateNotif("Reconnecting...");
                    if (bridge.reconnect(cameraEnabled)) {
                        pingFailCount = 0;
                        postStatus("Reconnected");
                        updateNotif("Publishing sensors...");
                    } else {
                        postStatus("Reconnect failed — retrying in 10s");
                    }
                }
            }
            scheduleHealthCheck();
        }, 5000);
    }

    /* ── SensorEventListener (fires on main Looper) ────────── */

    private long sensorLogCounter = 0;

    @Override
    public void onSensorChanged(SensorEvent e) {
        int type = e.sensor.getType();
        /* Log first few callbacks to debug sensor types */
        if (sensorLogCounter < 10) {
            Log.i(TAG, "Sensor callback: type=" + type + " name=" + e.sensor.getName()
                    + " val[0]=" + e.values[0]);
            sensorLogCounter++;
        }

        switch (type) {
            case Sensor.TYPE_ACCELEROMETER:
                latestAccel = e.values.clone(); break;
            case Sensor.TYPE_GYROSCOPE:
                latestGyro = e.values.clone(); break;
            case Sensor.TYPE_ROTATION_VECTOR:
            case Sensor.TYPE_GAME_ROTATION_VECTOR:
                float[] q = new float[4];
                SensorManager.getQuaternionFromVector(q, e.values);
                latestQuat = new float[]{q[1], q[2], q[3], q[0]}; break;
            default:
                /* Samsung vendor rotation vector? Try matching by name */
                if (e.sensor.getName().toLowerCase().contains("rotation")) {
                    float[] q2 = new float[4];
                    SensorManager.getQuaternionFromVector(q2, e.values);
                    latestQuat = new float[]{q2[1], q2[2], q2[3], q2[0]};
                }
                break;
        }
    }

    @Override public void onAccuracyChanged(Sensor s, int a) { }

    /* ── Foreground service ────────────────────────────────── */

    private void promoteToForeground() {
        int fgsType = 0;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED)
            fgsType |= ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                == PackageManager.PERMISSION_GRANTED)
            fgsType |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
        if (fgsType == 0)
            fgsType = ServiceInfo.FOREGROUND_SERVICE_TYPE_MANIFEST;

        try {
            ServiceCompat.startForeground(this, NOTIF_ID, buildNotif("Starting..."), fgsType);
        } catch (Exception e) {
            Log.e(TAG, "startForeground failed", e);
            stopSelf();
        }
    }

    private void createNotifChannel() {
        NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "ROVAC Sensors",
                NotificationManager.IMPORTANCE_LOW);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.createNotificationChannel(ch);
    }

    private Notification buildNotif(String text) {
        Intent tap = new Intent(this, MainActivity.class);
        tap.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 0, tap,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Intent stop = new Intent(this, SensorService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE);

        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("ROVAC Sensor Node")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_compass)
                .setContentIntent(pi)
                .addAction(android.R.drawable.ic_media_pause, "Stop", stopPi)
                .setOngoing(true)
                .build();
    }

    private void updateNotif(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.notify(NOTIF_ID, buildNotif(text));
    }

    /* ── Helpers ───────────────────────────────────────────── */

    /** Decode JPEG, scale down, re-encode at low quality to fit within MTU */
    private static byte[] recompressJpeg(byte[] jpeg, int maxW, int maxH, int quality) {
        try {
            Bitmap bmp = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.length);
            if (bmp == null) return null;
            /* Scale to maxW x maxH preserving aspect ratio */
            int w = bmp.getWidth(), h = bmp.getHeight();
            float scale = Math.min((float) maxW / w, (float) maxH / h);
            if (scale < 1.0f) {
                int nw = (int)(w * scale), nh = (int)(h * scale);
                bmp = Bitmap.createScaledBitmap(bmp, nw, nh, true);
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream(4096);
            bmp.compress(Bitmap.CompressFormat.JPEG, quality, out);
            return out.toByteArray();
        } catch (Exception e) {
            Log.e(TAG, "JPEG recompress failed", e);
            return null;
        }
    }

    private void postStatus(String msg) {
        Log.i(TAG, msg);
        if (statusListener != null) statusListener.onStatus(msg);
    }

    public static void stop(Context ctx) {
        Intent i = new Intent(ctx, SensorService.class);
        i.setAction(ACTION_STOP);
        ctx.startService(i);
    }
}
