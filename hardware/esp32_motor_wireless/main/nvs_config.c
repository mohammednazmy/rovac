/*
 * nvs_config.c — NVS-backed persistent configuration
 */
#include "nvs_config.h"

#include <string.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "sdkconfig.h"

static const char *TAG = "nvs_config";

static esp_err_t load_str(nvs_handle_t h, const char *key,
                          char *buf, size_t buf_sz, const char *def)
{
    size_t len = buf_sz;
    esp_err_t err = nvs_get_str(h, key, buf, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        strncpy(buf, def, buf_sz - 1);
        buf[buf_sz - 1] = '\0';
        return ESP_OK;
    }
    return err;
}

esp_err_t nvs_config_init(motor_wireless_config_t *cfg)
{
    // Initialize NVS flash partition
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
        err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition truncated, erasing...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    nvs_handle_t h;
    err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        // First boot — no namespace yet, use all defaults
        ESP_LOGI(TAG, "No NVS data found, using compiled defaults");
        strncpy(cfg->wifi_ssid, CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_SSID, NVS_STR_MAX);
        strncpy(cfg->wifi_pass, CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_PASS, NVS_STR_MAX);
        strncpy(cfg->wifi_ip, CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_IP, NVS_STR_MAX);
        strncpy(cfg->gateway_ip, CONFIG_MOTOR_WIRELESS_DEFAULT_GATEWAY_IP, NVS_STR_MAX);
        strncpy(cfg->netmask, CONFIG_MOTOR_WIRELESS_DEFAULT_NETMASK, NVS_STR_MAX);
        strncpy(cfg->agent_ip, CONFIG_MOTOR_WIRELESS_DEFAULT_AGENT_IP, NVS_STR_MAX);
        cfg->agent_port = CONFIG_MOTOR_WIRELESS_DEFAULT_AGENT_PORT;
        return ESP_OK;
    }
    ESP_ERROR_CHECK(err);

    load_str(h, "wifi_ssid", cfg->wifi_ssid, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_SSID);
    load_str(h, "wifi_pass", cfg->wifi_pass, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_PASS);
    load_str(h, "wifi_ip", cfg->wifi_ip, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_WIFI_IP);
    load_str(h, "gateway_ip", cfg->gateway_ip, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_GATEWAY_IP);
    load_str(h, "netmask", cfg->netmask, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_NETMASK);
    load_str(h, "agent_ip", cfg->agent_ip, NVS_STR_MAX,
             CONFIG_MOTOR_WIRELESS_DEFAULT_AGENT_IP);

    uint16_t port = CONFIG_MOTOR_WIRELESS_DEFAULT_AGENT_PORT;
    err = nvs_get_u16(h, "agent_port", &port);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to read agent_port: %s", esp_err_to_name(err));
    }
    cfg->agent_port = port;

    nvs_close(h);
    ESP_LOGI(TAG, "Config loaded: SSID=%s IP=%s Agent=%s:%u",
             cfg->wifi_ssid, cfg->wifi_ip, cfg->agent_ip, cfg->agent_port);
    return ESP_OK;
}

esp_err_t nvs_config_set_str(const char *key, const char *value)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err = nvs_set_str(h, key, value);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "NVS set %s = %s", key, value);
    } else {
        ESP_LOGE(TAG, "NVS set %s failed: %s", key, esp_err_to_name(err));
    }
    return err;
}

esp_err_t nvs_config_set_u16(const char *key, uint16_t value)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err = nvs_set_u16(h, key, value);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "NVS set %s = %u", key, value);
    }
    return err;
}

esp_err_t nvs_config_reset(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err = nvs_erase_all(h);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    ESP_LOGW(TAG, "NVS namespace '%s' erased", NVS_NAMESPACE);
    return err;
}

void nvs_config_dump(const motor_wireless_config_t *cfg)
{
    printf("NVS Config:\n");
    printf("  wifi_ssid  = %s\n", cfg->wifi_ssid);
    printf("  wifi_pass  = %s\n", cfg->wifi_pass);
    printf("  wifi_ip    = %s\n", cfg->wifi_ip);
    printf("  gateway_ip = %s\n", cfg->gateway_ip);
    printf("  netmask    = %s\n", cfg->netmask);
    printf("  agent_ip   = %s\n", cfg->agent_ip);
    printf("  agent_port = %u\n", cfg->agent_port);
}
