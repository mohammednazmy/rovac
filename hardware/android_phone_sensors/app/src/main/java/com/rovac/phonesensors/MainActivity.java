package com.rovac.phonesensors;

import android.Manifest;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.SurfaceTexture;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.view.Surface;
import android.view.TextureView;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

/**
 * UI controller with real-time sensor display and auto-connect.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "RovacPhone";
    private static final int PERM_CODE = 100;
    private static final String PREFS = "rovac_settings";

    private TextView statusText, imuAccelText, imuGyroText, imuOrientText;
    private TextView gpsText, cameraText, statsText;
    private Button connectBtn, settingsBtn;
    private TextureView cameraPreview;
    private Surface previewSurface;

    private SensorService service;
    private boolean bound = false;
    private boolean autoConnectPending = false;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setContentView(R.layout.activity_main);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        statusText    = findViewById(R.id.statusText);
        imuAccelText  = findViewById(R.id.imuAccelText);
        imuGyroText   = findViewById(R.id.imuGyroText);
        imuOrientText = findViewById(R.id.imuOrientText);
        gpsText       = findViewById(R.id.gpsText);
        cameraText    = findViewById(R.id.cameraText);
        statsText     = findViewById(R.id.statsText);
        connectBtn    = findViewById(R.id.connectButton);
        settingsBtn   = findViewById(R.id.settingsButton);

        cameraPreview = findViewById(R.id.cameraPreview);
        cameraPreview.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override public void onSurfaceTextureAvailable(@NonNull SurfaceTexture st, int w, int h) {
                st.setDefaultBufferSize(320, 240); /* match camera output size */
                previewSurface = new Surface(st);
                Log.i(TAG, "Preview surface available: " + w + "x" + h + " (buffer=320x240)");
                /* Pass to service — camera may need to restart with this surface */
                if (service != null) service.setPreviewSurface(previewSurface);
            }
            @Override public void onSurfaceTextureSizeChanged(@NonNull SurfaceTexture st, int w, int h) {}
            @Override public boolean onSurfaceTextureDestroyed(@NonNull SurfaceTexture st) {
                previewSurface = null; return true;
            }
            @Override public void onSurfaceTextureUpdated(@NonNull SurfaceTexture st) {}
        });

        connectBtn.setOnClickListener(v -> {
            if (service != null && service.isRunning()) {
                service.stopSensor();
                connectBtn.setText("Connect");
                /* Disable auto-connect when manually disconnected */
                getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putBoolean("auto_connect", false).apply();
            } else {
                requestPermsThenStart();
            }
        });

        settingsBtn.setOnClickListener(v ->
            startActivity(new Intent(this, SettingsActivity.class)));

        /* Check if auto-connect is enabled */
        if (getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("auto_connect", false)) {
            autoConnectPending = true;
        }
    }

    @Override
    protected void onStart() {
        super.onStart();
        Intent i = new Intent(this, SensorService.class);
        bindService(i, connection, Context.BIND_AUTO_CREATE);
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (bound) { unbindService(connection); bound = false; }
    }

    /* ── Service binding ───────────────────────────────────── */

    private final ServiceConnection connection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            service = ((SensorService.LocalBinder) binder).getService();
            bound = true;
            service.setStatusListener(statusListener);
            if (previewSurface != null) service.setPreviewSurface(previewSurface);
            if (service.isRunning()) {
                connectBtn.setText("Disconnect");
            } else if (autoConnectPending) {
                autoConnectPending = false;
                requestPermsThenStart();
            }
        }
        @Override
        public void onServiceDisconnected(ComponentName name) {
            bound = false; service = null;
        }
    };

    private final SensorService.StatusListener statusListener = new SensorService.StatusListener() {
        @Override
        public void onStatus(String msg) {
            runOnUiThread(() -> statusText.setText(msg));
        }

        @Override
        public void onImuUpdate(long count, float[] acc, float[] gyro, float[] quat) {
            runOnUiThread(() -> {
                imuAccelText.setText(String.format("X: %+7.3f  Y: %+7.3f  Z: %+7.3f", acc[0], acc[1], acc[2]));
                imuGyroText.setText(String.format("X: %+7.4f  Y: %+7.4f  Z: %+7.4f", gyro[0], gyro[1], gyro[2]));
                imuOrientText.setText(String.format("X: %+.4f  Y: %+.4f  Z: %+.4f  W: %+.4f",
                        quat[0], quat[1], quat[2], quat[3]));
                statsText.setText(String.format("IMU: %d msgs @ 50Hz", count));
            });
        }

        @Override
        public void onGpsUpdate(double lat, double lon, double alt) {
            runOnUiThread(() -> gpsText.setText(String.format(
                    "Lat: %.6f\nLon: %.6f\nAlt: %.1f m", lat, lon, alt)));
        }

        @Override
        public void onCameraFrame(int bytes) {
            runOnUiThread(() -> cameraText.setText(String.format("JPEG: %d bytes", bytes)));
        }
    };

    /* ── Permissions ───────────────────────────────────────── */

    private void requestPermsThenStart() {
        String[] needed = getNeededPerms();
        if (needed.length > 0) {
            ActivityCompat.requestPermissions(this, needed, PERM_CODE);
        } else {
            startPublishing();
        }
    }

    private String[] getNeededPerms() {
        java.util.List<String> perms = new java.util.ArrayList<>();
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED)
            perms.add(Manifest.permission.ACCESS_FINE_LOCATION);
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED)
            perms.add(Manifest.permission.CAMERA);
        if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED)
            perms.add(Manifest.permission.POST_NOTIFICATIONS);
        return perms.toArray(new String[0]);
    }

    @Override
    public void onRequestPermissionsResult(int code, @NonNull String[] perms, @NonNull int[] res) {
        super.onRequestPermissionsResult(code, perms, res);
        if (code == PERM_CODE) startPublishing();
    }

    /* ── Start publishing via service ──────────────────────── */

    private void startPublishing() {
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        String ip    = p.getString("agent_ip",   "192.168.1.200");
        String port  = p.getString("agent_port", "8888");
        int domain   = p.getInt("domain_id", 42);
        boolean cam  = p.getBoolean("camera_enabled", false);
        Log.i("RovacPhone", "startPublishing: camera_enabled=" + cam
                + " all_keys=" + p.getAll());

        /* Enable auto-connect for next launch */
        p.edit().putBoolean("auto_connect", true).apply();

        ContextCompat.startForegroundService(this, new Intent(this, SensorService.class));

        cameraText.setText(cam ? "Enabled — waiting for frames..." : "Disabled (enable in Settings)");

        if (service != null) {
            if (previewSurface != null) service.setPreviewSurface(previewSurface);
            service.startSensor(ip, port, domain, cam);
            connectBtn.setText("Disconnect");
        } else {
            statusText.setText("Starting service...");
            connectBtn.postDelayed(() -> {
                if (service != null) {
                    service.startSensor(ip, port, domain, cam);
                    connectBtn.setText("Disconnect");
                }
            }, 500);
        }
    }
}
