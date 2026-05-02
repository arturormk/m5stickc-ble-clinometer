#pragma once
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "../model/DeviceState.h"

#define BLE_DEVICE_NAME  "M5-NexStar-Level"
#define BLE_SERVICE_UUID "7d91b000-8f3b-4b63-b6a4-5d1e6b7a1000"
#define BLE_CMD_UUID     "7d91b001-8f3b-4b63-b6a4-5d1e6b7a1000"
#define BLE_RESP_UUID    "7d91b002-8f3b-4b63-b6a4-5d1e6b7a1000"
#define BLE_STATUS_UUID  "7d91b003-8f3b-4b63-b6a4-5d1e6b7a1000"

class BleManager {
public:
    void begin(DeviceState* state);
    void update(DeviceState& state);

    void sendResponse(const char* msg);
    void sendEvent(const char* msg);

private:
    BLEServer*         _pServer     = nullptr;
    BLECharacteristic* _pRespChar   = nullptr;
    BLECharacteristic* _pStatusChar = nullptr;

    bool     _wasConnected   = false;
    uint32_t _lastStatusMs   = 0;

    void _updateStatusChar(const DeviceState& state);
};
