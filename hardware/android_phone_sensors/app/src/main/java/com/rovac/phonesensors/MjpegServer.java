package com.rovac.phonesensors;

import android.util.Log;

import java.io.*;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Simple MJPEG-over-HTTP server. Serves camera frames at
 * http://<phone-ip>:8080/stream as multipart/x-mixed-replace.
 *
 * Also serves a single JPEG snapshot at http://<phone-ip>:8080/frame.jpg
 */
public class MjpegServer {

    private static final String TAG = "MjpegServer";
    private static final String BOUNDARY = "rovac_frame";
    public static final int PORT = 8080;

    private ServerSocket serverSocket;
    private ExecutorService executor;
    private final CopyOnWriteArrayList<OutputStream> clients = new CopyOnWriteArrayList<>();
    private volatile byte[] latestFrame;
    private volatile boolean running = false;

    public void start() {
        if (running) return;
        running = true;
        executor = Executors.newCachedThreadPool();
        executor.submit(this::acceptLoop);
        Log.i(TAG, "MJPEG server started on port " + PORT);
    }

    public void stop() {
        running = false;
        try { if (serverSocket != null) serverSocket.close(); } catch (Exception e) { /* ok */ }
        for (OutputStream os : clients) {
            try { os.close(); } catch (Exception e) { /* ok */ }
        }
        clients.clear();
        if (executor != null) executor.shutdownNow();
        Log.i(TAG, "MJPEG server stopped");
    }

    /** Called from camera callback with each new JPEG frame */
    public void pushFrame(byte[] jpeg) {
        latestFrame = jpeg;

        /* Send to all connected streaming clients */
        for (OutputStream os : clients) {
            try {
                os.write(("--" + BOUNDARY + "\r\n").getBytes());
                os.write("Content-Type: image/jpeg\r\n".getBytes());
                os.write(("Content-Length: " + jpeg.length + "\r\n\r\n").getBytes());
                os.write(jpeg);
                os.write("\r\n".getBytes());
                os.flush();
            } catch (Exception e) {
                /* Client disconnected */
                clients.remove(os);
                try { os.close(); } catch (Exception ex) { /* ok */ }
            }
        }
    }

    private void acceptLoop() {
        try {
            serverSocket = new ServerSocket(PORT);
            serverSocket.setReuseAddress(true);
            Log.i(TAG, "Listening on port " + PORT);

            while (running) {
                Socket client = serverSocket.accept();
                executor.submit(() -> handleClient(client));
            }
        } catch (Exception e) {
            if (running) Log.e(TAG, "Accept error", e);
        }
    }

    private void handleClient(Socket socket) {
        try {
            BufferedReader in = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            OutputStream out = new BufferedOutputStream(socket.getOutputStream());

            /* Read HTTP request line */
            String requestLine = in.readLine();
            if (requestLine == null) { socket.close(); return; }

            /* Skip remaining headers */
            String line;
            while ((line = in.readLine()) != null && !line.isEmpty()) { /* skip */ }

            String path = requestLine.split(" ")[1];
            Log.i(TAG, "Request: " + path + " from " + socket.getInetAddress());

            if (path.equals("/frame.jpg") || path.equals("/frame")) {
                /* Single JPEG snapshot */
                byte[] frame = latestFrame;
                if (frame != null) {
                    out.write("HTTP/1.1 200 OK\r\n".getBytes());
                    out.write("Content-Type: image/jpeg\r\n".getBytes());
                    out.write(("Content-Length: " + frame.length + "\r\n").getBytes());
                    out.write("Connection: close\r\n\r\n".getBytes());
                    out.write(frame);
                } else {
                    out.write("HTTP/1.1 503 No Frame\r\nConnection: close\r\n\r\n".getBytes());
                }
                out.flush();
                socket.close();

            } else if (path.equals("/stream") || path.equals("/")) {
                /* MJPEG stream — keep connection open */
                out.write("HTTP/1.1 200 OK\r\n".getBytes());
                out.write(("Content-Type: multipart/x-mixed-replace; boundary=" + BOUNDARY + "\r\n").getBytes());
                out.write("Cache-Control: no-cache\r\n".getBytes());
                out.write("Connection: keep-alive\r\n\r\n".getBytes());
                out.flush();

                clients.add(out);
                Log.i(TAG, "Stream client connected (" + clients.size() + " total)");

                /* Keep socket alive until client disconnects or server stops */
                try {
                    while (running && !socket.isClosed()) {
                        Thread.sleep(1000);
                    }
                } catch (InterruptedException e) { /* ok */ }

                clients.remove(out);
                socket.close();

            } else if (path.startsWith("/torch")) {
                /* Torch control: /torch/on or /torch/off */
                boolean on = path.contains("on") || path.contains("1");
                if (torchCallback != null) torchCallback.onTorch(on);
                String body = "torch=" + (on ? "on" : "off") + "\n";
                out.write("HTTP/1.1 200 OK\r\n".getBytes());
                out.write("Content-Type: text/plain\r\n".getBytes());
                out.write(("Content-Length: " + body.length() + "\r\n").getBytes());
                out.write("Access-Control-Allow-Origin: *\r\n".getBytes());
                out.write("Connection: close\r\n\r\n".getBytes());
                out.write(body.getBytes());
                out.flush();
                socket.close();

            } else {
                /* 404 */
                String body = "ROVAC Phone Camera\n\n/stream - MJPEG stream\n/frame.jpg - Single snapshot\n/torch/on - Flashlight on\n/torch/off - Flashlight off\n";
                out.write("HTTP/1.1 404 Not Found\r\n".getBytes());
                out.write("Content-Type: text/plain\r\n".getBytes());
                out.write(("Content-Length: " + body.length() + "\r\n").getBytes());
                out.write("Connection: close\r\n\r\n".getBytes());
                out.write(body.getBytes());
                out.flush();
                socket.close();
            }
        } catch (Exception e) {
            if (running) Log.w(TAG, "Client error: " + e.getMessage());
            try { socket.close(); } catch (Exception ex) { /* ok */ }
        }
    }

    /* Torch control callback */
    public interface TorchCallback {
        void onTorch(boolean enabled);
    }
    private TorchCallback torchCallback;
    public void setTorchCallback(TorchCallback cb) { torchCallback = cb; }

    public int getClientCount() { return clients.size(); }
    public boolean isRunning() { return running; }
}
