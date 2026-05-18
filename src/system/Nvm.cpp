#include "Nvm.h"
#include <Preferences.h>
#include <M5Unified.h>
#include <time.h>

static const char* kNs = "clino";

static uint32_t readRtcEpoch() {
    if (!M5.Rtc.isEnabled() || M5.Rtc.getVoltLow()) return 0;
    m5::rtc_datetime_t dt;
    if (!M5.Rtc.getDateTime(&dt) || dt.date.year < 2020) return 0;
    struct tm utc = {};
    utc.tm_year  = dt.date.year - 1900;
    utc.tm_mon   = dt.date.month - 1;
    utc.tm_mday  = dt.date.date;
    utc.tm_hour  = dt.time.hours;
    utc.tm_min   = dt.time.minutes;
    utc.tm_sec   = dt.time.seconds;
    utc.tm_isdst = 0;
    time_t t = mktime(&utc);
    return (t > 0) ? (uint32_t)t : 0;
}

void Nvm::_applyData(DeviceState& state, ImuManager& imu) {
    Preferences prefs;
    prefs.begin(kNs, true);

    bool   hasTz  = prefs.isKey("tz");
    String tz     = hasTz ? prefs.getString("tz", "") : "";

    bool  hasCal = prefs.isKey("cal_gx");
    float gx = 0.0f, gy = 0.0f, gz = 1.0f;
    if (hasCal) {
        gx = prefs.getFloat("cal_gx", 0.0f);
        gy = prefs.getFloat("cal_gy", 0.0f);
        gz = prefs.getFloat("cal_gz", 1.0f);
    }

    uint8_t  sidOn  = prefs.getUChar("sid_on",  0);
    uint32_t sidLst = prefs.getULong("sid_lst",  0);
    uint32_t sidRtc = prefs.getULong("sid_rtc",  0);

    prefs.end();

    if (hasTz) {
        strncpy(state.timezoneLabel, tz.c_str(), sizeof(state.timezoneLabel) - 1);
        state.timezoneLabel[sizeof(state.timezoneLabel) - 1] = '\0';
    }

    if (hasCal) {
        imu.calibrateFrom(gx, gy, gz);
    }

    if (sidOn == 1 && sidRtc > 0) {
        uint32_t nowRtc = readRtcEpoch();
        if (nowRtc >= sidRtc) {
            int64_t elapsedSolar = (int64_t)(nowRtc - sidRtc);
            int64_t elapsedSid   = elapsedSolar * 1002738LL / 1000000LL;
            int64_t lstNow       = ((int64_t)sidLst + elapsedSid) % 86400LL;
            if (lstNow < 0) lstNow += 86400LL;
            state.timeEpochSec    = (time_t)lstNow;
            state.timeSetAtMillis = millis();
            state.siderealMode    = true;
        }
    }
}

void Nvm::load(DeviceState& state, ImuManager& imu) {
    Preferences prefs;
    prefs.begin(kNs, true);
    uint8_t valid = prefs.getUChar("valid", 0);
    prefs.end();
    if (valid != 1) return;
    _applyData(state, imu);
}

bool Nvm::saveAll(const DeviceState& state, ImuManager& imu) {
    float gx, gy, gz;
    imu.getCalibrationRef(gx, gy, gz);

    uint8_t  sidOn  = state.siderealMode ? 1 : 0;
    uint32_t sidLst = 0;
    uint32_t sidRtc = 0;
    if (sidOn) {
        time_t cur = deviceCurrentTime(state);
        sidLst = (uint32_t)(cur % 86400);
        sidRtc = readRtcEpoch();
    }

    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putString("tz",      state.timezoneLabel);
    prefs.putFloat ("cal_gx",  gx);
    prefs.putFloat ("cal_gy",  gy);
    prefs.putFloat ("cal_gz",  gz);
    prefs.putUChar ("sid_on",  sidOn);
    prefs.putULong ("sid_lst", sidLst);
    prefs.putULong ("sid_rtc", sidRtc);
    prefs.putUChar ("valid",   1);   // written last — atomic commit
    prefs.end();
    return true;
}

void Nvm::clear() {
    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putUChar("valid", 0);
    prefs.end();
}

void Nvm::restore(DeviceState& state, ImuManager& imu) {
    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putUChar("valid", 1);
    prefs.end();
    _applyData(state, imu);
}

void Nvm::formatStatus(char* buf, size_t len) {
    Preferences prefs;
    prefs.begin(kNs, true);

    uint8_t valid  = prefs.getUChar("valid", 0);
    bool    hasTz  = prefs.isKey("tz");
    String  tz     = hasTz ? prefs.getString("tz", "") : "";
    bool    hasCal = prefs.isKey("cal_gx");
    float   gx = 0.0f, gy = 0.0f, gz = 1.0f;
    if (hasCal) {
        gx = prefs.getFloat("cal_gx", 0.0f);
        gy = prefs.getFloat("cal_gy", 0.0f);
        gz = prefs.getFloat("cal_gz", 1.0f);
    }
    uint8_t  sidOn  = prefs.getUChar("sid_on",  0);
    uint32_t sidLst = prefs.getULong("sid_lst",  0);
    uint32_t sidRtc = prefs.getULong("sid_rtc",  0);

    prefs.end();

    // Format lst as HH:MM:SS
    char lstBuf[12] = "(none)";
    if (sidOn && sidLst < 86400) {
        uint32_t h = sidLst / 3600, m = (sidLst % 3600) / 60, s = sidLst % 60;
        snprintf(lstBuf, sizeof(lstBuf), "%02u:%02u:%02u", h, m, s);
    }

    // Format sid_rtc anchor as ISO8601 UTC
    char rtcBuf[24] = "(none)";
    if (sidOn && sidRtc > 0) {
        time_t t = (time_t)sidRtc;
        struct tm utc;
        gmtime_r(&t, &utc);
        snprintf(rtcBuf, sizeof(rtcBuf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
                 utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday,
                 utc.tm_hour, utc.tm_min, utc.tm_sec);
    }

    char calBuf[40];
    if (hasCal)
        snprintf(calBuf, sizeof(calBuf), "%+.4f,%+.4f,%+.4f", gx, gy, gz);
    else
        snprintf(calBuf, sizeof(calBuf), "(none)");

    snprintf(buf, len,
             "PERSIST valid=%d tz=%s cal=%s sid=%s lst=%s rtc=%s",
             valid,
             hasTz && tz.length() ? tz.c_str() : "(none)",
             calBuf,
             sidOn ? "on" : "off",
             lstBuf,
             rtcBuf);
}
