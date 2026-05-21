#include "Nvm.h"
#include <Preferences.h>
#include <M5Unified.h>
#include <time.h>
#include <math.h>
#include <esp_timer.h>

static const char* kNs = "clino";

// Read the hardware RTC and return a UTC epoch, or 0 if unavailable / not set.
static time_t readRtcEpoch() {
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
    time_t t = mktime(&utc);   // TZ=UTC0 makes this behave as timegm
    return (t > 0) ? t : 0;
}

void Nvm::rebuildAnchor(DeviceState& s) {
    time_t utc = readRtcEpoch();
    s.utcAnchorSec = utc;
    s.anchorUs     = esp_timer_get_time();

    if (utc == 0) {
        s.lstPhaseQ40 = 0;
        return;
    }

    // Linear GMST formula: error < 0.006 s at year 2100 — adequate for amateur use.
    double lon  = isnan(s.longitudeDeg) ? 0.0 : (double)s.longitudeDeg;
    int64_t dt  = (int64_t)utc - (int64_t)J2000_UNIX_SEC;
    double gmst = fmod(GMST_J2000_SEC + (double)dt * 1.002737909350795, 86400.0);
    if (gmst < 0.0) gmst += 86400.0;
    double lst  = fmod(gmst + lon * 240.0, 86400.0);
    if (lst  < 0.0) lst  += 86400.0;

    double fraction = lst / 86400.0;
    s.lstPhaseQ40 = (uint64_t)(fraction * (double)SIDEREAL_SCALE_Q40 + 0.5)
                    & (SIDEREAL_SCALE_Q40 - 1ULL);
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

    int32_t tzOffset = prefs.getInt("tz_offset", 0);
    bool    hasLon   = prefs.isKey("longitude");
    float   lon      = hasLon ? prefs.getFloat("longitude", 0.0f) : NAN;

    prefs.end();

    if (hasTz) {
        strncpy(state.timezoneLabel, tz.c_str(), sizeof(state.timezoneLabel) - 1);
        state.timezoneLabel[sizeof(state.timezoneLabel) - 1] = '\0';
    }
    state.timezoneOffsetSec = tzOffset;
    state.longitudeDeg      = lon;

    if (hasCal) {
        imu.calibrateFrom(gx, gy, gz);
    }

    // Derive sidereal mode from label; fix label if longitude is absent.
    bool isSid = (strcmp(state.timezoneLabel, "LST") == 0 ||
                  strcmp(state.timezoneLabel, "GST") == 0);
    if (isSid && isnan(state.longitudeDeg)) {
        strncpy(state.timezoneLabel, "GST", sizeof(state.timezoneLabel) - 1);
    }
    state.siderealMode = isSid;
}

void Nvm::load(DeviceState& state, ImuManager& imu) {
    Preferences prefs;
    prefs.begin(kNs, true);
    uint8_t valid = prefs.getUChar("valid", 0);
    prefs.end();
    if (valid == 1) _applyData(state, imu);
    rebuildAnchor(state);   // always rebuild from RTC regardless of NVS state
}

bool Nvm::saveAll(const DeviceState& state, ImuManager& imu) {
    float gx, gy, gz;
    imu.getCalibrationRef(gx, gy, gz);

    Preferences prefs;
    prefs.begin(kNs, false);
    prefs.putString("tz",        state.timezoneLabel);
    prefs.putInt   ("tz_offset", state.timezoneOffsetSec);
    prefs.putFloat ("cal_gx",    gx);
    prefs.putFloat ("cal_gy",    gy);
    prefs.putFloat ("cal_gz",    gz);
    if (!isnan(state.longitudeDeg))
        prefs.putFloat("longitude", state.longitudeDeg);
    else
        prefs.remove("longitude");
    prefs.putUChar("valid", 1);   // written last — atomic commit
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
    rebuildAnchor(state);
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
    int32_t tzOffset = prefs.getInt("tz_offset", 0);
    bool    hasLon   = prefs.isKey("longitude");
    float   lon      = hasLon ? prefs.getFloat("longitude", 0.0f) : NAN;

    prefs.end();

    char calBuf[40];
    if (hasCal)
        snprintf(calBuf, sizeof(calBuf), "%+.4f,%+.4f,%+.4f", gx, gy, gz);
    else
        snprintf(calBuf, sizeof(calBuf), "(none)");

    char lonBuf[16];
    if (hasLon)
        snprintf(lonBuf, sizeof(lonBuf), "%.4f", lon);
    else
        snprintf(lonBuf, sizeof(lonBuf), "(none)");

    snprintf(buf, len,
             "PERSIST valid=%d tz=%s tz_offset=%d lon=%s cal=%s",
             valid,
             hasTz && tz.length() ? tz.c_str() : "(none)",
             tzOffset,
             lonBuf,
             calBuf);
}
