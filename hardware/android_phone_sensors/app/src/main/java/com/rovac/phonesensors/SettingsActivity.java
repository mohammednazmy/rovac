package com.rovac.phonesensors;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;

/**
 * Settings screen for Agent IP, port, domain ID, and camera toggle.
 */
public class SettingsActivity extends AppCompatActivity {

    private static final String PREFS = "rovac_settings";

    private EditText ipField, portField, domainField;
    private Switch cameraSwitch, autoConnectSwitch;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setContentView(R.layout.activity_settings);

        ipField      = findViewById(R.id.agentIpField);
        portField    = findViewById(R.id.agentPortField);
        domainField  = findViewById(R.id.domainIdField);
        cameraSwitch = findViewById(R.id.cameraSwitch);
        autoConnectSwitch = findViewById(R.id.autoConnectSwitch);
        Button saveBtn = findViewById(R.id.saveButton);

        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        ipField.setText(p.getString("agent_ip", "192.168.1.200"));
        portField.setText(p.getString("agent_port", "9090"));
        domainField.setText(String.valueOf(p.getInt("domain_id", 42)));
        cameraSwitch.setChecked(p.getBoolean("camera_enabled", false));
        autoConnectSwitch.setChecked(p.getBoolean("auto_connect", false));

        saveBtn.setOnClickListener(v -> {
            int domain;
            try {
                domain = Integer.parseInt(domainField.getText().toString().trim());
            } catch (NumberFormatException e) {
                domain = 42;
            }

            p.edit()
                .putString("agent_ip", ipField.getText().toString().trim())
                .putString("agent_port", portField.getText().toString().trim())
                .putInt("domain_id", domain)
                .putBoolean("camera_enabled", cameraSwitch.isChecked())
                .putBoolean("auto_connect", autoConnectSwitch.isChecked())
                .apply();

            Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show();
            finish();
        });
    }
}
