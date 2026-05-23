#pragma once
#include <Arduino.h>
#include <time.h>
#include <math.h>
#include <esp_timer.h>

// Sidereal / GMST constants (used in inline functions below)
static constexpr uint64_t SIDEREAL_SCALE_Q40 = (1ULL << 40);
// round(2^40 * 1.002737909350795 / 86400)
static constexpr uint64_t SIDEREAL_INC_Q40   = 12760671ULL;
// 2000-01-01 12:00:00 UTC as Unix epoch
static constexpr uint64_t J2000_UNIX_SEC      = 946728000ULL;
// GMST at J2000.0 in seconds of time
static constexpr double   GMST_J2000_SEC      = 67310.54841;

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
    float    gravY;           // raw filtered gravity Y component (device frame, before calibration)
    float    accMag;          // filtered gravity vector magnitude in g (~1.0 when stationary; data quality indicator)
    uint32_t tiltTimestampMs;

    time_t   utcAnchorSec;       // UTC epoch at last sync (0 = not set)
    int64_t  anchorUs;           // esp_timer_get_time() at last sync
    uint64_t lstPhaseQ40;        // LST phase at anchor (Q40 fixed-point)
    int32_t  timezoneOffsetSec;  // UTC+N offset in seconds for solar display
    float    longitudeDeg;       // Observer longitude °East; NAN = not set
    char     timezoneLabel[32];  // e.g. "UTC", "+09:00", "JST", "LST", "GST"
    bool     siderealMode;       // true when displaying LST/GST

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
    uint8_t  messageFontCode;    // 0/2=Font4(def) 1=Font2 3=Font6 4=Font8 5=JGoth16 6=JGoth24

    bool     pendingReboot;

    volatile char pendingBleResponse[160];
    volatile bool pendingBleResponseReady;
    volatile char pendingBleEvent[64];
    volatile bool pendingBleEventReady;
    volatile int16_t pendingBleHelpLine;  // -1 = idle; 0..N = next line to send; N+1 = send "OK"
    volatile bool bleClientWantsNewline;
};

// Returns current UTC epoch, advancing from the anchor.
inline time_t deviceCurrentTime(const DeviceState& s) {
    if (s.utcAnchorSec == 0) return 0;
    int64_t elapsedUs = esp_timer_get_time() - s.anchorUs;
    return s.utcAnchorSec + (time_t)(elapsedUs / 1000000LL);
}

// Returns current LST/GST as seconds of day [0, 86400). Pure integer arithmetic.
inline uint32_t currentLstSeconds(const DeviceState& s) {
    if (s.utcAnchorSec == 0) return 0;
    int64_t elapsedUs   = esp_timer_get_time() - s.anchorUs;
    uint64_t elapsedSec = (uint64_t)(elapsedUs / 1000000LL);
    uint64_t phase = (s.lstPhaseQ40 + elapsedSec * SIDEREAL_INC_Q40) & (SIDEREAL_SCALE_Q40 - 1ULL);
    return (uint32_t)((phase * 86400ULL) >> 40);
}
