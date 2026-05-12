#include "OV2640.h"

esp_err_t OV2640::init(camera_config_t config)
{
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
        return err;
    }
    return ESP_OK;
}

void OV2640::run(void)
{
    if (fb)
    {
        esp_camera_fb_return(fb);
    }
    fb = esp_camera_fb_get();
}

size_t OV2640::getSize(void)
{
    if (fb)
    {
        return fb->len;
    }
    return 0;
}

uint8_t *OV2640::getfb(void)
{
    if (fb)
    {
        return fb->buf;
    }
    return NULL;
}

int OV2640::getWidth(void)
{
    if (fb)
    {
        return fb->width;
    }
    return 0;
}

int OV2640::getHeight(void)
{
    if (fb)
    {
        return fb->height;
    }
    return 0;
}

framesize_t OV2640::getFrameSize(void)
{
    return (fb) ? (framesize_t)0 : (framesize_t)0;
}

pixformat_t OV2640::getPixelFormat(void)
{
    if (fb)
    {
        return fb->format;
    }
    return PIXFORMAT_RGB565;
}

void OV2640::setFrameSize(framesize_t size)
{
    sensor_t *s = esp_camera_sensor_get();
    if (s)
    {
        s->set_framesize(s, size);
    }
}

void OV2640::setPixelFormat(pixformat_t format)
{
}
