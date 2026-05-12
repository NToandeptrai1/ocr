#ifndef OV2640_H
#define OV2640_H

#include "esp_camera.h"

class OV2640
{
public:
    esp_err_t init(camera_config_t config);
    void run(void);
    size_t getSize(void);
    uint8_t *getfb(void);
    int getWidth(void);
    int getHeight(void);
    framesize_t getFrameSize(void);
    pixformat_t getPixelFormat(void);

    void setFrameSize(framesize_t size);
    void setPixelFormat(pixformat_t format);

private:
    camera_fb_t *fb = NULL;
};

#endif
