/*
 * wifi.c — WiFi STA with static IP and auto-reconnect
 */
#include "wifi.h"

#include <string.h>
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

static const char *TAG = "wifi";

#define WIFI_CONNECTED_BIT  BIT0

static EventGroupHandle_t s_wifi_events;
static int s_retry_count = 0;
static bool s_started = false;

static void event_handler(void *arg, esp_event_base_t base,
                          int32_t event_id, void *event_data)
{
    if (base == WIFI_EVENT) {
        switch (event_id) {
        case WIFI_EVENT_STA_START:
            ESP_LOGI(TAG, "STA started, connecting...");
            esp_wifi_connect();
            break;
        case WIFI_EVENT_STA_DISCONNECTED: {
            wifi_event_sta_disconnected_t *dis =
                (wifi_event_sta_disconnected_t *)event_data;
            xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
            // Exponential backoff: 1s, 2s, 4s, 8s, max 10s
            int delay_s = (1 << s_retry_count);
            if (delay_s > 10) delay_s = 10;
            s_retry_count++;
            ESP_LOGW(TAG, "Disconnected (reason=%d), retry #%d in %ds",
                     dis->reason, s_retry_count, delay_s);
            vTaskDelay(pdMS_TO_TICKS(delay_s * 1000));
            esp_wifi_connect();
            break;
        }
        default:
            break;
        }
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Connected! IP=" IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_count = 0;
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
    }
}

esp_err_t wifi_init(const motor_wireless_config_t *cfg)
{
    s_wifi_events = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    esp_netif_t *netif = esp_netif_create_default_wifi_sta();

    // Static IP configuration
    esp_netif_dhcpc_stop(netif);
    esp_netif_ip_info_t ip_info = {0};
    esp_netif_str_to_ip4(cfg->wifi_ip, &ip_info.ip);
    esp_netif_str_to_ip4(cfg->gateway_ip, &ip_info.gw);
    esp_netif_str_to_ip4(cfg->netmask, &ip_info.netmask);
    ESP_ERROR_CHECK(esp_netif_set_ip_info(netif, &ip_info));

    // DNS — use gateway as DNS server (common for home routers)
    esp_netif_dns_info_t dns = {0};
    dns.ip.u_addr.ip4 = ip_info.gw;
    dns.ip.type = ESP_IPADDR_TYPE_V4;
    esp_netif_set_dns_info(netif, ESP_NETIF_DNS_MAIN, &dns);

    wifi_init_config_t wifi_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, NULL));

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, cfg->wifi_ssid,
            sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, cfg->wifi_pass,
            sizeof(wifi_config.sta.password) - 1);
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Disable power save for minimum latency (robot control)
    esp_wifi_set_ps(WIFI_PS_NONE);

    s_started = true;
    ESP_LOGI(TAG, "WiFi STA init: SSID=%s, StaticIP=%s",
             cfg->wifi_ssid, cfg->wifi_ip);
    return ESP_OK;
}

bool wifi_is_connected(void)
{
    if (!s_started) return false;
    EventBits_t bits = xEventGroupGetBits(s_wifi_events);
    return (bits & WIFI_CONNECTED_BIT) != 0;
}

int8_t wifi_get_rssi(void)
{
    if (!wifi_is_connected()) return 0;
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        return ap.rssi;
    }
    return 0;
}

void wifi_reconnect(void)
{
    if (s_started) {
        s_retry_count = 0;
        esp_wifi_disconnect();
    }
}
