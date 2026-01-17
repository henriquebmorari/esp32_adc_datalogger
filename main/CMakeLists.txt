idf_component_register(SRCS "adc_datalogger.c"
                    INCLUDE_DIRS "."
                    REQUIRES nvs_flash esp_wifi esp_netif esp_event mqtt esp_adc esp_timer)
