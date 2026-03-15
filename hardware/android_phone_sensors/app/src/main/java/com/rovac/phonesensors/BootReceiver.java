package com.rovac.phonesensors;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;
import androidx.core.content.ContextCompat;

/**
 * Starts the sensor service automatically on device boot
 * if auto-connect is enabled in settings.
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";
    private static final String PREFS = "rovac_settings";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;

        SharedPreferences p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!p.getBoolean("auto_connect", false)) {
            Log.i(TAG, "Auto-connect disabled, skipping");
            return;
        }

        Log.i(TAG, "Boot completed — starting ROVAC sensor service");

        /* Start the service — it will read settings and connect on its own */
        Intent serviceIntent = new Intent(context, SensorService.class);
        serviceIntent.setAction(SensorService.ACTION_BOOT_START);
        ContextCompat.startForegroundService(context, serviceIntent);
    }
}
