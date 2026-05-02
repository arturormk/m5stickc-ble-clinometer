#pragma once
#include <Arduino.h>
#include <time.h>

#define SCREEN_CLINOMETER 0
#define SCREEN_TIME       1
#define SCREEN_RADEC      2
#define SCREEN_ALTAZ      3
#define SCREEN_MESSAGE    4

// Button bitmask constants
#define BTN_MASK_M5  0x01
#define BTN_MASK_A   0x02
#define BTN_MASK_B   0x04
#define BTN_MASK_ANY 0x07

struct DeviceState {
    int      screenIndex;
    int      prevScreenIndex;

    bool     bleConnected;
    float    batteryVoltage;

    float    tiltXDeg;
    float    tiltYDeg;
    uint32_t tiltTimestampMs;

    time_t   timeEpochSec;       // 0 = not set
    uint32_t timeSetAtMillis;

    char raText[32];
    char decText[32];
    char altText[32];
    char azText[32];

    bool     streamEnabled;
    uint32_t streamPeriodMs;
    uint32_t lastStreamMs;

    bool     messageActive;
    char     messageText[128];
    uint32_t messageExpiresAtMs;  // 0 = persistent
    bool     messagePersistent;
    uint8_t  messageAwaitButtons; // bitmask: BTN_MASK_*

    volatile char pendingBleResponse[160];
    volatile bool pendingBleResponseReady;
    volatile char pendingBleEvent[64];
    volatile bool pendingBleEventReady;
};

inline time_t deviceCurrentTime(const DeviceState& s) {
    if (s.timeEpochSec == 0) return 0;
    return s.timeEpochSec + (time_t)((millis() - s.timeSetAtMillis) / 1000UL);
}
