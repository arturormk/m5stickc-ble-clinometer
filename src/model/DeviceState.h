#pragma once
#include <Arduino.h>
#include <time.h>

#define MELODY_MAX_NOTES 32

struct MelodyNote {
    uint16_t freqHz;  // 0 = rest
    uint16_t durMs;
};

#define SCREEN_CLINOMETER 0
#define SCREEN_TIME       1
#define SCREEN_RADEC      2
#define SCREEN_ALTAZ      3
#define SCREEN_BATTERY    4
#define SCREEN_MESSAGE    5

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
    int      batteryLevel;    // 0-100, or -1 if unknown

    bool     imuAvailable;
    float    pitchDeg;
    float    rollDeg;
    float    gravX;           // raw filtered gravity X component (device frame, before calibration)
    uint32_t tiltTimestampMs;

    time_t   timeEpochSec;       // 0 = not set
    uint32_t timeSetAtMillis;
    char     timezoneLabel[16];  // e.g. "UTC", "+01:00", "CET"; empty = not set
    bool     siderealMode;       // if true, tick at sidereal rate (366.2422/365.2422)

    char raText[32];
    char decText[32];
    char altText[32];
    char azText[32];

    bool     streamEnabled;
    uint32_t streamPeriodMs;
    uint32_t lastStreamMs;

    bool     nightMode;

    MelodyNote       melodyNotes[MELODY_MAX_NOTES];
    volatile int     melodyPendingLength;
    volatile bool    melodyPending;
    int              melodyLength;
    int              melodyNoteIdx;
    uint32_t         melodyNoteUntilMs;

    bool     messageActive;
    char     messageText[128];
    uint32_t messageExpiresAtMs;  // 0 = persistent
    bool     messagePersistent;
    uint8_t  messageAwaitButtons; // bitmask: BTN_MASK_*

    volatile char pendingBleResponse[160];
    volatile bool pendingBleResponseReady;
    volatile char pendingBleEvent[64];
    volatile bool pendingBleEventReady;
    volatile bool pendingBleHelpReady;
    volatile bool bleClientWantsNewline;
};

inline time_t deviceCurrentTime(const DeviceState& s) {
    if (s.timeEpochSec == 0) return 0;
    uint32_t elapsedMs = millis() - s.timeSetAtMillis;
    if (s.siderealMode) {
        // Sidereal rate ≈ 1002738/1000000; use 64-bit to avoid overflow in product
        elapsedMs = (uint32_t)((uint64_t)elapsedMs * 1002738ULL / 1000000ULL);
    }
    return s.timeEpochSec + (time_t)(elapsedMs / 1000UL);
}
