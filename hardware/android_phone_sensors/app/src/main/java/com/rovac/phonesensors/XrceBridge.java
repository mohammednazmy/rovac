package com.rovac.phonesensors;

import android.util.Base64;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * rosbridge WebSocket client for publishing phone sensor data.
 * Replaces the previous JNI/native XRCE-DDS transport with a pure-Java
 * OkHttp WebSocket client that speaks the rosbridge v2.0 protocol.
 *
 * All sends are thread-safe (OkHttp WebSocket.send is thread-safe).
 */
public class XrceBridge {

    private static final String TAG = "XrceBridge";

    private OkHttpClient client;
    private WebSocket webSocket;
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private volatile boolean entitiesCreated = false;
    private volatile boolean cameraAdvertised = false;

    /* Saved connection params for reconnect */
    private String savedIp;
    private String savedPort;
    private int savedDomainId;

    /* Topic names */
    private static final String TOPIC_IMU = "/phone/imu";
    private static final String TOPIC_GPS = "/phone/gps/fix";
    private static final String TOPIC_IMAGE = "/phone/camera/image_raw/compressed";

    /* ROS2 message types */
    private static final String TYPE_IMU = "sensor_msgs/msg/Imu";
    private static final String TYPE_GPS = "sensor_msgs/msg/NavSatFix";
    private static final String TYPE_IMAGE = "sensor_msgs/msg/CompressedImage";

    /**
     * Open a WebSocket connection to the rosbridge server.
     * Blocks until connected or timeout (5s).
     */
    public boolean connect(String ip, String port, int domainId) {
        savedIp = ip;
        savedPort = port;
        savedDomainId = domainId;

        try {
            if (client != null) {
                disconnect();
            }

            client = new OkHttpClient.Builder()
                    .connectTimeout(5, TimeUnit.SECONDS)
                    .readTimeout(0, TimeUnit.MILLISECONDS) /* no read timeout for WebSocket */
                    .writeTimeout(5, TimeUnit.SECONDS)
                    .pingInterval(10, TimeUnit.SECONDS)    /* OkHttp-level keepalive */
                    .build();

            String url = "ws://" + ip + ":" + port;
            Request request = new Request.Builder().url(url).build();
            Log.i(TAG, "Connecting to " + url);

            CountDownLatch latch = new CountDownLatch(1);

            webSocket = client.newWebSocket(request, new WebSocketListener() {
                @Override
                public void onOpen(WebSocket ws, Response response) {
                    Log.i(TAG, "WebSocket connected to " + url);
                    connected.set(true);
                    latch.countDown();
                }

                @Override
                public void onMessage(WebSocket ws, String text) {
                    /* rosbridge may send responses; log but ignore */
                    Log.d(TAG, "WS recv: " + text.substring(0, Math.min(text.length(), 200)));
                }

                @Override
                public void onClosing(WebSocket ws, int code, String reason) {
                    Log.w(TAG, "WebSocket closing: " + code + " " + reason);
                    connected.set(false);
                    entitiesCreated = false;
                }

                @Override
                public void onClosed(WebSocket ws, int code, String reason) {
                    Log.i(TAG, "WebSocket closed: " + code + " " + reason);
                    connected.set(false);
                    entitiesCreated = false;
                }

                @Override
                public void onFailure(WebSocket ws, Throwable t, Response response) {
                    Log.e(TAG, "WebSocket failure: " + t.getMessage());
                    connected.set(false);
                    entitiesCreated = false;
                    latch.countDown(); /* unblock connect() on failure */
                }
            });

            /* Wait up to 5 seconds for connection */
            boolean opened = latch.await(5, TimeUnit.SECONDS);
            if (!opened || !connected.get()) {
                Log.e(TAG, "Connection timed out or failed");
                closeInternal();
                return false;
            }
            return true;

        } catch (Exception e) {
            Log.e(TAG, "Connect error", e);
            closeInternal();
            return false;
        }
    }

    /**
     * Send rosbridge "advertise" messages for each topic.
     */
    public boolean createPublishers(boolean withCamera) {
        if (!connected.get() || webSocket == null) return false;

        try {
            /* Advertise IMU */
            sendAdvertise(TOPIC_IMU, TYPE_IMU);

            /* Advertise GPS */
            sendAdvertise(TOPIC_GPS, TYPE_GPS);

            /* Advertise CompressedImage */
            if (withCamera) {
                sendAdvertise(TOPIC_IMAGE, TYPE_IMAGE);
                cameraAdvertised = true;
            } else {
                cameraAdvertised = false;
            }

            entitiesCreated = true;
            Log.i(TAG, "Publishers created (camera=" + (withCamera ? "yes" : "no") + ")");
            return true;

        } catch (Exception e) {
            Log.e(TAG, "createPublishers error", e);
            return false;
        }
    }

    /**
     * Publish an IMU message.
     */
    public boolean publishImu(int sec, int nsec, String frameId,
                              double ox, double oy, double oz, double ow,
                              double avx, double avy, double avz,
                              double lax, double lay, double laz) {
        if (!entitiesCreated || !connected.get()) return false;

        try {
            JSONObject msg = new JSONObject();

            /* header */
            JSONObject header = new JSONObject();
            JSONObject stamp = new JSONObject();
            stamp.put("sec", sec);
            stamp.put("nanosec", nsec);
            header.put("stamp", stamp);
            header.put("frame_id", frameId);
            msg.put("header", header);

            /* orientation */
            JSONObject orientation = new JSONObject();
            orientation.put("x", ox);
            orientation.put("y", oy);
            orientation.put("z", oz);
            orientation.put("w", ow);
            msg.put("orientation", orientation);
            msg.put("orientation_covariance", zeroCov9());

            /* angular_velocity */
            JSONObject angVel = new JSONObject();
            angVel.put("x", avx);
            angVel.put("y", avy);
            angVel.put("z", avz);
            msg.put("angular_velocity", angVel);
            msg.put("angular_velocity_covariance", zeroCov9());

            /* linear_acceleration */
            JSONObject linAcc = new JSONObject();
            linAcc.put("x", lax);
            linAcc.put("y", lay);
            linAcc.put("z", laz);
            msg.put("linear_acceleration", linAcc);
            msg.put("linear_acceleration_covariance", zeroCov9());

            return sendPublish(TOPIC_IMU, msg);

        } catch (Exception e) {
            Log.e(TAG, "publishImu error", e);
            return false;
        }
    }

    /**
     * Publish a NavSatFix message.
     */
    public boolean publishNavSatFix(int sec, int nsec, String frameId,
                                    int navStatus, int service,
                                    double lat, double lon, double alt,
                                    int covType) {
        if (!entitiesCreated || !connected.get()) return false;

        try {
            JSONObject msg = new JSONObject();

            /* header */
            JSONObject header = new JSONObject();
            JSONObject stamp = new JSONObject();
            stamp.put("sec", sec);
            stamp.put("nanosec", nsec);
            header.put("stamp", stamp);
            header.put("frame_id", frameId);
            msg.put("header", header);

            /* status */
            JSONObject status = new JSONObject();
            status.put("status", navStatus);
            status.put("service", service);
            msg.put("status", status);

            /* position */
            msg.put("latitude", lat);
            msg.put("longitude", lon);
            msg.put("altitude", alt);

            /* covariance */
            msg.put("position_covariance", zeroCov9());
            msg.put("position_covariance_type", covType);

            return sendPublish(TOPIC_GPS, msg);

        } catch (Exception e) {
            Log.e(TAG, "publishNavSatFix error", e);
            return false;
        }
    }

    /**
     * Publish a CompressedImage message.
     * The JPEG data is base64-encoded for the rosbridge JSON transport.
     */
    public boolean publishCompressedImage(int sec, int nsec, String frameId,
                                          String format, byte[] data) {
        if (!entitiesCreated || !connected.get()) return false;

        try {
            JSONObject msg = new JSONObject();

            /* header */
            JSONObject header = new JSONObject();
            JSONObject stamp = new JSONObject();
            stamp.put("sec", sec);
            stamp.put("nanosec", nsec);
            header.put("stamp", stamp);
            header.put("frame_id", frameId);
            msg.put("header", header);

            /* format + data */
            msg.put("format", format);
            msg.put("data", Base64.encodeToString(data, Base64.NO_WRAP));

            return sendPublish(TOPIC_IMAGE, msg);

        } catch (Exception e) {
            Log.e(TAG, "publishCompressedImage error", e);
            return false;
        }
    }

    /**
     * Check WebSocket connection health.
     * OkHttp's ping interval handles keepalive; we just check the connected flag.
     */
    public boolean ping(int timeoutMs) {
        return connected.get() && webSocket != null;
    }

    /**
     * Disconnect and reconnect with fresh WebSocket + re-advertise topics.
     */
    public boolean reconnect(boolean withCamera) {
        Log.w(TAG, "Reconnecting to " + savedIp + ":" + savedPort + " ...");
        disconnect();

        if (!connect(savedIp, savedPort, savedDomainId)) return false;
        if (!createPublishers(withCamera)) {
            disconnect();
            return false;
        }
        Log.i(TAG, "Reconnected successfully");
        return true;
    }

    /**
     * No-op for rosbridge (WebSocket is async, no spin needed).
     */
    public void spin(int timeoutMs) {
        /* rosbridge is fully async — nothing to do */
    }

    /**
     * Send unadvertise for all topics and close the WebSocket.
     */
    public void disconnect() {
        entitiesCreated = false;

        if (webSocket != null && connected.get()) {
            try {
                sendUnadvertise(TOPIC_IMU);
                sendUnadvertise(TOPIC_GPS);
                if (cameraAdvertised) {
                    sendUnadvertise(TOPIC_IMAGE);
                }
            } catch (Exception e) {
                Log.w(TAG, "Unadvertise error (non-fatal)", e);
            }
        }

        closeInternal();
        Log.i(TAG, "Disconnected");
    }

    /**
     * Return WebSocket connection state.
     */
    public boolean isConnected() {
        return connected.get();
    }

    /* ── Internal helpers ───────────────────────────────────────── */

    private void sendAdvertise(String topic, String type) throws Exception {
        JSONObject msg = new JSONObject();
        msg.put("op", "advertise");
        msg.put("topic", topic);
        msg.put("type", type);
        String json = msg.toString();
        Log.d(TAG, "advertise: " + topic + " [" + type + "]");
        webSocket.send(json);
    }

    private void sendUnadvertise(String topic) throws Exception {
        JSONObject msg = new JSONObject();
        msg.put("op", "unadvertise");
        msg.put("topic", topic);
        webSocket.send(msg.toString());
    }

    private boolean sendPublish(String topic, JSONObject rosMsg) throws Exception {
        if (webSocket == null || !connected.get()) return false;

        JSONObject envelope = new JSONObject();
        envelope.put("op", "publish");
        envelope.put("topic", topic);
        envelope.put("msg", rosMsg);

        return webSocket.send(envelope.toString());
    }

    private JSONArray zeroCov9() throws Exception {
        JSONArray arr = new JSONArray();
        for (int i = 0; i < 9; i++) arr.put(0.0);
        return arr;
    }

    private void closeInternal() {
        connected.set(false);
        entitiesCreated = false;

        if (webSocket != null) {
            try {
                webSocket.close(1000, "disconnect");
            } catch (Exception e) {
                try { webSocket.cancel(); } catch (Exception ex) { /* ok */ }
            }
            webSocket = null;
        }

        if (client != null) {
            try {
                client.dispatcher().executorService().shutdown();
                client.connectionPool().evictAll();
            } catch (Exception e) { /* ok */ }
            client = null;
        }
    }
}
