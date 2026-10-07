idf_component_register(SRCS "muse_main.c" INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_driver_usb_serial_jtag json esp_timer)
