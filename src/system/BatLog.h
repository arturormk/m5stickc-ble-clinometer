#pragma once
#include <Arduino.h>
#include "../model/DeviceState.h"

enum BatLogType : uint8_t {
    BAT_LOG_SAMPLE         = 0,
    BAT_LOG_BOOT           = 1,
    BAT_LOG_SLEEP_ENTER    = 2,   // reserved for future software sleep
    BAT_LOG_BLE_CONNECT    = 3,
    BAT_LOG_BLE_DISCONNECT = 4,
    BAT_LOG_SCREEN_CHANGE  = 5,
};

struct BatLogEntry {   // 12 bytes
    uint32_t utcSec;   // UTC epoch (0 = not set)
    uint16_t batMv;    // millivolts (0 = N/A)
    uint8_t  batLevel; // 0-100, or 0xFF = unknown
    uint8_t  type;     // BatLogType
    uint8_t  screenIdx;
    uint8_t  pad[3];
};
static_assert(sizeof(BatLogEntry) == 12, "BatLogEntry must be 12 bytes");

class BatLog {
public:
    void begin();
    void start(const DeviceState& state, uint32_t intervalSec = 300);
    void stop();
    void tick(const DeviceState& state);
    void onEvent(BatLogType type, const DeviceState& state);
    void clear();

    bool        isActive() const { return _active; }
    int         count()    const { return (int)_count; }
    BatLogEntry entry(int i) const;

private:
    static constexpr int kCapacity = 128;
    BatLogEntry _buf[kCapacity];
    uint16_t    _head      = 0;
    uint16_t    _count     = 0;
    bool        _active    = false;
    uint32_t    _intervalMs   = 300000;
    uint32_t    _lastSampleMs = 0;
    uint8_t     _lastScreen   = 0xFF;  // 0xFF = not initialised

    void _append(const BatLogEntry& e);
    void _flush();
    void _flushActive();
};
