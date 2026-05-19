package com.rovac.phonesensors;

import android.content.Context;
import android.graphics.*;
import android.media.Image;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.util.Size;

import androidx.annotation.NonNull;
import androidx.annotation.OptIn;
import androidx.camera.core.*;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * CameraX capture with preview + torch (flashlight) support.
 * Delivers JPEG frames via callback and shows preview on a PreviewView.
 */
public class Camera2JpegCapture {

    private static final String TAG = "CamXCapture";
    private static final int TARGET_W = 640, TARGET_H = 480;
    private static final int JPEG_QUALITY = 70;
    private static final long MIN_INTERVAL_MS = 200; /* 5 FPS */

    public interface JpegCallback {
        void onJpeg(byte[] jpeg, int w, int h, long timestampMs);
    }

    private final Context ctx;
    private JpegCallback callback;
    private PreviewView previewView;
    private ProcessCameraProvider cameraProvider;
    private androidx.camera.core.Camera camera; /* CameraX Camera — for torch control */
    private ExecutorService analysisExecutor;
    private long lastFrameMs = 0;
    private boolean torchEnabled = false;

    /* No-op for API compat */
    public void setPreviewSurface(android.view.Surface s) { }

    public Camera2JpegCapture(@NonNull Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public void setCallback(JpegCallback cb) { this.callback = cb; }

    /** Set the PreviewView to show live camera feed on the phone screen */
    public void setPreviewView(PreviewView view) { this.previewView = view; }

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
        cameraProvider.unbindAll();

        /* Preview use case — shows live feed on the PreviewView */
        Preview preview = new Preview.Builder()
                .setTargetResolution(new Size(TARGET_W, TARGET_H))
                .build();

        if (previewView != null) {
            preview.setSurfaceProvider(previewView.getSurfaceProvider());
            Log.i(TAG, "Preview connected to PreviewView");
        }

        /* Image analysis use case — captures YUV frames for JPEG conversion */
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
                try { Thread.sleep(Math.min(MIN_INTERVAL_MS - elapsed, 150)); }
                catch (InterruptedException e) { /* ok */ }
                return;
            }
            lastFrameMs = now;

            try {
                Bitmap bmp = imageProxy.toBitmap();
                imageProxy.close();

                if (bmp == null) return;
                int w = bmp.getWidth(), h = bmp.getHeight();

                /* Scale down if needed */
                if (w > TARGET_W || h > TARGET_H) {
                    float s = Math.min((float) TARGET_W / w, (float) TARGET_H / h);
                    Bitmap scaled = Bitmap.createScaledBitmap(bmp, (int)(w*s), (int)(h*s), false);
                    bmp.recycle();
                    bmp = scaled;
                }

                ByteArrayOutputStream out = new ByteArrayOutputStream(8192);
                bmp.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out);
                bmp.recycle();
                byte[] jpeg = out.toByteArray();

                if (callback != null) {
                    callback.onJpeg(jpeg, TARGET_W, TARGET_H, now);
                }
            } catch (Exception e) {
                Log.e(TAG, "Frame error", e);
                try { imageProxy.close(); } catch (Exception ex) { /* ok */ }
            }
        });

        CameraSelector selector = CameraSelector.DEFAULT_BACK_CAMERA;

        try {
            androidx.lifecycle.LifecycleOwner owner = new androidx.lifecycle.LifecycleOwner() {
                private final androidx.lifecycle.LifecycleRegistry reg =
                    new androidx.lifecycle.LifecycleRegistry(this);
                { reg.setCurrentState(androidx.lifecycle.Lifecycle.State.RESUMED); }
                @NonNull @Override
                public androidx.lifecycle.Lifecycle getLifecycle() { return reg; }
            };

            /* Bind both Preview + ImageAnalysis */
            camera = cameraProvider.bindToLifecycle(owner, selector, preview, analysis);
            Log.i(TAG, "CameraX bound with preview + analysis at " + TARGET_W + "x" + TARGET_H);

            /* Restore torch state */
            if (torchEnabled && camera != null) {
                camera.getCameraControl().enableTorch(true);
            }
        } catch (Exception e) {
            Log.e(TAG, "CameraX bind failed", e);
        }
    }

    /* ── Torch (flashlight) control ──────────────────────────── */

    public void setTorch(boolean enabled) {
        torchEnabled = enabled;
        if (camera != null) {
            camera.getCameraControl().enableTorch(enabled);
            Log.i(TAG, "Torch " + (enabled ? "ON" : "OFF"));
        }
    }

    public boolean isTorchEnabled() { return torchEnabled; }

    public void toggleTorch() { setTorch(!torchEnabled); }

    public void close() {
        if (camera != null) {
            try { camera.getCameraControl().enableTorch(false); } catch (Exception e) { /* ok */ }
            camera = null;
        }
        if (cameraProvider != null) {
            new Handler(Looper.getMainLooper()).post(() -> {
                try { cameraProvider.unbindAll(); } catch (Exception e) { /* ok */ }
            });
            cameraProvider = null;
        }
        if (analysisExecutor != null) {
            analysisExecutor.shutdown();
            analysisExecutor = null;
        }
        Log.i(TAG, "Closed");
    }
}
