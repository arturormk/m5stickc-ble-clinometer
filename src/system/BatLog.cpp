#include "BatLog.h"
#include <Preferences.h>

static const char* kNs = "batlog";

void BatLog::begin() {
    Preferences prefs;
    prefs.begin(kNs, true);  // read-only
    _active = prefs.getUChar("active", 0) != 0;
    uint32_t iv = prefs.getUInt("interval", 300);
    if (iv < 10) iv = 10;
    _intervalMs = iv * 1000;
    _head  = prefs.getUShort("head", 0);
    _count = prefs.getUShort("cnt",  0);
    if (_count > (uint16_t)kCapacity) _count = (uint16_t)kCapacity;
    if (_head  >= (uint16_t)kCapacity) _head  = 0;
    prefs.getBytes("data", _buf, sizeof(_buf));
    prefs.end();
    _lastSampleMs = millis();
}

void BatLog::start(const DeviceState& state, uint32_t intervalSec) {
    if (intervalSec < 10)    intervalSec = 10;
    if (intervalSec > 86400) intervalSec = 86400;
    _active       = true;
    _intervalMs   = intervalSec * 1000;
    _lastSampleMs = millis();
    _lastScreen   = (uint8_t)state.screenIndex;  // prevent spurious SCR_CHG on first tick
    _flush();
    onEvent(BAT_LOG_BOOT, state);
}

void BatLog::stop() {
    _active = false;
    _flushActive();
}

void BatLog::clear() {
    _head  = 0;
    _count = 0;
    memset(_buf, 0, sizeof(_buf));
    _flush();
}

BatLogEntry BatLog::entry(int i) const {
    int start = ((int)_head - (int)_count + kCapacity * 2) % kCapacity;
    return _buf[(start + i) % kCapacity];
}

void BatLog::tick(const DeviceState& state) {
    if (!_active) return;

    // Initialize _lastScreen on first tick after begin() (reboot with active log)
    if (_lastScreen == 0xFF)
        _lastScreen = (uint8_t)state.screenIndex;

    // Screen change detection
    if ((uint8_t)state.screenIndex != _lastScreen) {
        _lastScreen = (uint8_t)state.screenIndex;
        onEvent(BAT_LOG_SCREEN_CHANGE, state);
    }

    // Periodic sample
    uint32_t now = millis();
    if ((now - _lastSampleMs) >= _intervalMs) {
        _lastSampleMs = now;
        onEvent(BAT_LOG_SAMPLE, state);
    }
}

void BatLog::onEvent(BatLogType type, const DeviceState& state) {
    if (!_active) return;
    BatLogEntry e{};
    e.type      = (uint8_t)type;
    e.batLevel  = (state.batteryLevel < 0 || state.batteryLevel > 100)
                  ? 0xFF : (uint8_t)state.batteryLevel;
    e.batMv     = (state.batteryVoltage > 0.01f && state.batteryVoltage <= 5.0f)
                  ? (uint16_t)(state.batteryVoltage * 1000.0f + 0.5f) : 0;
    e.screenIdx = (uint8_t)state.screenIndex;
    time_t t    = deviceCurrentTime(state);
    e.utcSec    = (t > 0) ? (uint32_t)t : 0;
    _append(e);
}

void BatLog::_append(const BatLogEntry& e) {
    _buf[_head] = e;
    _head = (uint16_t)((_head + 1) % kCapacity);
    if (_count < (uint16_t)kCapacity) _count++;
    _flush();
}

void BatLog::_flush() {
    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putUChar ("active",   _active ? 1 : 0);
    prefs.putUInt  ("interval", _intervalMs / 1000);
    prefs.putUShort("head",     _head);
    prefs.putUShort("cnt",      _count);
    prefs.putBytes ("data",     _buf, sizeof(_buf));
    prefs.end();
}

void BatLog::_flushActive() {
    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putUChar("active", _active ? 1 : 0);
    prefs.end();
}
