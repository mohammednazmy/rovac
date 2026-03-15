package com.rovac.phonesensors;

import android.content.Context;
import android.graphics.*;
import android.media.Image;
import android.util.Log;
import android.util.Size;

import androidx.annotation.NonNull;
import androidx.annotation.OptIn;
import androidx.camera.core.*;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.LifecycleOwner;
import androidx.lifecycle.LifecycleService;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * CameraX-based capture. Handles Samsung device quirks automatically.
 * Uses ImageAnalysis to get YUV frames, converts to JPEG.
 */
public class Camera2JpegCapture {

    private static final String TAG = "CamXCapture";
    private static final int TARGET_W = 320, TARGET_H = 240;
    private static final int JPEG_QUALITY = 40;
    private static final long MIN_INTERVAL_MS = 500; /* 2 FPS */

    public interface JpegCallback {
        void onJpeg(byte[] jpeg, int w, int h, long timestampMs);
    }

    private final Context ctx;
    private JpegCallback callback;
    private ProcessCameraProvider cameraProvider;
    private ExecutorService analysisExecutor;
    private long lastFrameMs = 0;

    /* These are unused now but kept for API compatibility */
    public void setPreviewSurface(android.view.Surface s) { /* no-op with CameraX */ }

    public Camera2JpegCapture(@NonNull Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public void setCallback(JpegCallback cb) { this.callback = cb; }

    public void open() {
        analysisExecutor = Executors.newSingleThreadExecutor();

        ListenableFuture<ProcessCameraProvider> future =
                ProcessCameraProvider.getInstance(ctx);

        future.addListener(() -> {
            try {
                cameraProvider = future.get();
                bindCamera();
            } catch (Exception e) {
                Log.e(TAG, "CameraX init failed", e);
            }
        }, ContextCompat.getMainExecutor(ctx));
    }

    @OptIn(markerClass = ExperimentalGetImage.class)
    private void bindCamera() {
        if (cameraProvider == null) return;

        /* Unbind everything first */
        cameraProvider.unbindAll();

        /* Image analysis use case — gets YUV frames */
        ImageAnalysis analysis = new ImageAnalysis.Builder()
                .setTargetResolution(new Size(TARGET_W, TARGET_H))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build();

        analysis.setAnalyzer(analysisExecutor, imageProxy -> {
            long now = System.currentTimeMillis();
            long elapsed = now - lastFrameMs;
            if (elapsed < MIN_INTERVAL_MS) {
                imageProxy.close();
                /* Sleep to avoid busy-loop consuming CPU at 15 FPS */
                try { Thread.sleep(Math.min(MIN_INTERVAL_MS - elapsed, 200)); }
                catch (InterruptedException e) { /* ok */ }
                return;
            }
            lastFrameMs = now;

            try {
                /* Use BitmapFactory with inSampleSize to decode at reduced resolution
                 * directly — much faster than full NV21 conversion + scale */
                Bitmap bmp = imageProxy.toBitmap();
                imageProxy.close(); /* close immediately — don't hold the buffer */

                if (bmp == null) { Log.w(TAG, "toBitmap returned null"); return; }
                int w = bmp.getWidth(), h = bmp.getHeight();
                Log.i(TAG, "Step1: Bitmap " + w + "x" + h);

                /* Scale down */
                if (w > TARGET_W || h > TARGET_H) {
                    float s = Math.min((float) TARGET_W / w, (float) TARGET_H / h);
                    Bitmap scaled = Bitmap.createScaledBitmap(bmp, (int)(w*s), (int)(h*s), false);
                    bmp.recycle();
                    bmp = scaled;
                }
                Log.i(TAG, "Step2: Scaled to " + bmp.getWidth() + "x" + bmp.getHeight());

                ByteArrayOutputStream out = new ByteArrayOutputStream(4096);
                bmp.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out);
                bmp.recycle();
                byte[] jpeg = out.toByteArray();
                Log.i(TAG, "Step3: JPEG " + jpeg.length + " bytes");

                if (callback != null) {
                    callback.onJpeg(jpeg, TARGET_W, TARGET_H, now);
                    Log.i(TAG, "Step4: Published");
                }
            } catch (Exception e) {
                Log.e(TAG, "Frame error", e);
                try { imageProxy.close(); } catch (Exception ex) { /* already closed */ }
            }
        });

        /* Select back camera */
        CameraSelector selector = CameraSelector.DEFAULT_BACK_CAMERA;

        /* Bind to a LifecycleOwner — use the Service if it's a LifecycleService,
         * otherwise create a minimal lifecycle */
        try {
            /* Use a custom LifecycleOwner in RESUMED state — guarantees
             * continuous frame delivery even from a background service. */
            androidx.lifecycle.LifecycleOwner owner = new androidx.lifecycle.LifecycleOwner() {
                private final androidx.lifecycle.LifecycleRegistry reg =
                    new androidx.lifecycle.LifecycleRegistry(this);
                { reg.setCurrentState(androidx.lifecycle.Lifecycle.State.RESUMED); }
                @NonNull @Override
                public androidx.lifecycle.Lifecycle getLifecycle() { return reg; }
            };
            cameraProvider.bindToLifecycle(owner, selector, analysis);
            Log.i(TAG, "CameraX bound — analyzing at " + TARGET_W + "x" + TARGET_H);
        } catch (Exception e) {
            Log.e(TAG, "CameraX bind failed", e);
        }
    }

    public void close() {
        if (cameraProvider != null) {
            /* Must unbind on main thread */
            try {
                android.os.Handler mainHandler = new android.os.Handler(android.os.Looper.getMainLooper());
                mainHandler.post(() -> {
                    try { cameraProvider.unbindAll(); } catch (Exception e) { /* ok */ }
                });
            } catch (Exception e) { /* ok */ }
            cameraProvider = null;
        }
        if (analysisExecutor != null) {
            analysisExecutor.shutdown();
            analysisExecutor = null;
        }
        Log.i(TAG, "Closed");
    }

    /** Convert ImageProxy (YUV_420_888) to scaled JPEG byte array */
    @OptIn(markerClass = ExperimentalGetImage.class)
    private static byte[] imageProxyToScaledJpeg(ImageProxy proxy, int maxW, int maxH, int quality) {
        Image image = proxy.getImage();
        if (image == null) return null;

        int w = image.getWidth(), h = image.getHeight();
        Image.Plane yPlane = image.getPlanes()[0];
        Image.Plane uPlane = image.getPlanes()[1];
        Image.Plane vPlane = image.getPlanes()[2];

        ByteBuffer yBuf = yPlane.getBuffer();
        ByteBuffer uBuf = uPlane.getBuffer();
        ByteBuffer vBuf = vPlane.getBuffer();

        int ySize = w * h;
        int uvSize = w * h / 2;
        byte[] nv21 = new byte[ySize + uvSize];

        /* Copy Y */
        int yStride = yPlane.getRowStride();
        if (yStride == w) {
            yBuf.get(nv21, 0, ySize);
        } else {
            for (int row = 0; row < h; row++) {
                yBuf.position(row * yStride);
                yBuf.get(nv21, row * w, w);
            }
        }

        /* Copy UV — interleave to NV21 */
        int uvPixelStride = vPlane.getPixelStride();
        int uvRowStride = vPlane.getRowStride();
        int uvH = h / 2, uvW = w / 2;
        for (int row = 0; row < uvH; row++) {
            for (int col = 0; col < uvW; col++) {
                int vIdx = row * uvRowStride + col * uvPixelStride;
                int uIdx = row * uPlane.getRowStride() + col * uPlane.getPixelStride();
                nv21[ySize + row * w + col * 2] = vBuf.get(vIdx);
                nv21[ySize + row * w + col * 2 + 1] = uBuf.get(uIdx);
            }
        }

        /* Compress YUV to JPEG, then scale down if larger than target */
        YuvImage yuv = new YuvImage(nv21, ImageFormat.NV21, w, h, null);
        ByteArrayOutputStream fullOut = new ByteArrayOutputStream(8192);
        yuv.compressToJpeg(new Rect(0, 0, w, h), quality, fullOut);

        if (w <= maxW && h <= maxH) {
            return fullOut.toByteArray();
        }

        /* Scale: decode JPEG → Bitmap → scale → re-encode */
        byte[] fullJpeg = fullOut.toByteArray();
        Bitmap bmp = BitmapFactory.decodeByteArray(fullJpeg, 0, fullJpeg.length);
        if (bmp == null) return fullJpeg;
        float scale = Math.min((float) maxW / w, (float) maxH / h);
        Bitmap scaled = Bitmap.createScaledBitmap(bmp, (int)(w * scale), (int)(h * scale), true);
        bmp.recycle();
        ByteArrayOutputStream out = new ByteArrayOutputStream(4096);
        scaled.compress(Bitmap.CompressFormat.JPEG, quality, out);
        scaled.recycle();
        return out.toByteArray();
    }
}
