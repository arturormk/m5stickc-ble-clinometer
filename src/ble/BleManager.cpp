#include "BleManager.h"
#include "../imu/ImuManager.h"
#include <time.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

// ---------------------------------------------------------------------------
// Module-level state accessible from callbacks
// ---------------------------------------------------------------------------

static DeviceState* s_state = nullptr;
static ImuManager*  s_imu   = nullptr;
static BLECharacteristic* s_pRespChar = nullptr;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static const char* screenName(int idx) {
    switch (idx) {
        case SCREEN_CLINOMETER: return "CLINOMETER";
        case SCREEN_TIME:       return "TIME";
        case SCREEN_RADEC:      return "RADEC";
        case SCREEN_ALTAZ:      return "ALTAZ";
        case SCREEN_BATTERY:    return "BATTERY";
        case SCREEN_MESSAGE:    return "MESSAGE";
        default:                return "UNKNOWN";
    }
}

static bool parseIso8601(const char* s, time_t* out, char* tzOut, size_t tzOutSize) {
    int y, mo, d, h, mi, sec, n = 0;
    if (sscanf(s, "%d-%d-%dT%d:%d:%d%n", &y, &mo, &d, &h, &mi, &sec, &n) < 6 || n == 0)
        return false;
    if (tzOut) tzOut[0] = '\0';
    const char* suffix = s + n;
    if (*suffix == 'Z' || *suffix == 'z') {
        if (tzOut) snprintf(tzOut, tzOutSize, "UTC");
    } else if (*suffix == '\0') {
        // bare datetime, no suffix — leave label empty
    } else if (*suffix == '+' || *suffix == '-') {
        if (tzOut) snprintf(tzOut, tzOutSize, "%s", suffix);
    } else {
        return false;
    }
    struct tm t = {};
    t.tm_year  = y - 1900;
    t.tm_mon   = mo - 1;
    t.tm_mday  = d;
    t.tm_hour  = h;
    t.tm_min   = mi;
    t.tm_sec   = sec;
    t.tm_isdst = 0;
    time_t result = mktime(&t);
    if (result == (time_t)-1) return false;
    *out = result;
    return true;
}

// Parses "HH:MM:SS" → seconds since midnight stored in *out.
static bool parseSiderealHMS(const char* s, time_t* out) {
    int h, m, sec;
    if (sscanf(s, "%d:%d:%d", &h, &m, &sec) != 3) return false;
    if (h < 0 || h > 23 || m < 0 || m > 59 || sec < 0 || sec > 59) return false;
    *out = (time_t)(h * 3600 + m * 60 + sec);
    return true;
}

static uint8_t parseMsgButtons(const char* token) {
    if (strcmp(token, "ANY") == 0) return BTN_MASK_ANY;
    uint8_t mask = 0;
    // Work on a copy so strtok_r doesn't break the original
    char buf[32];
    strncpy(buf, token, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    char* saveptr = nullptr;
    char* part = strtok_r(buf, ",", &saveptr);
    while (part) {
        if (strcmp(part, "M5") == 0) mask |= BTN_MASK_M5;
        else if (strcmp(part, "A") == 0) mask |= BTN_MASK_A;
        else if (strcmp(part, "B") == 0) mask |= BTN_MASK_B;
        part = strtok_r(nullptr, ",", &saveptr);
    }
    return mask;
}

// Build "YYYY-MM-DDTHH:MM:SSZ" from epoch
static void formatIso8601(time_t t, char* buf, size_t len) {
    struct tm ti;
    gmtime_r(&t, &ti);
    snprintf(buf, len, "%04d-%02d-%02dT%02d:%02d:%02dZ",
             ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
             ti.tm_hour, ti.tm_min, ti.tm_sec);
}

// Assemble the STATUS response line
static void buildStatusLine(const DeviceState& state, char* buf, size_t len) {
    snprintf(buf, len, "STATUS SCREEN=%s BLE=%d STREAM=%d BAT=%.2f NIGHT=%d",
             screenName(state.screenIndex),
             state.bleConnected ? 1 : 0,
             state.streamEnabled ? 1 : 0,
             state.batteryVoltage,
             state.nightMode ? 1 : 0);
}

// ---------------------------------------------------------------------------
// BEEP / melody helpers
// ---------------------------------------------------------------------------

static uint16_t noteFreq(int semitone, int octave) {
    int total = semitone + (octave - 4) * 12;
    return (uint16_t)(261.63f * powf(2.0f, total / 12.0f) + 0.5f);
}

static int parseMelody(const char* str, MelodyNote* notes, int maxNotes, int* errPos) {
    char buf[256];
    strncpy(buf, str, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    char* sp  = nullptr;
    char* tok = strtok_r(buf, " ", &sp);
    int count = 0;
    while (tok && count < maxNotes) {
        const char* p = tok;
        bool isRest   = (*p == '-');
        int semi = 0, octave = 5;
        if (!isRest) {
            switch (toupper((unsigned char)*p++)) {
                case 'C': semi =  0; break;
                case 'D': semi =  2; break;
                case 'E': semi =  4; break;
                case 'F': semi =  5; break;
                case 'G': semi =  7; break;
                case 'A': semi =  9; break;
                case 'B': semi = 11; break;
                default:
                    if (errPos) *errPos = (int)((p - 1) - buf) + 1;
                    return 0;
            }
            if (*p == '#') { semi++; p++; }
            else if (*p == 'b') { semi--; p++; }
        } else {
            p++;
        }
        while (*p == '\'') { octave++; p++; }
        while (*p == ',')  { octave--; p++; }
        int div = 4;
        if (isdigit((unsigned char)*p)) {
            div = 0;
            while (isdigit((unsigned char)*p)) div = div * 10 + (*p++ - '0');
        }
        if (div <= 0) div = 4;
        uint32_t dur = (4u * 250u) / (uint32_t)div;  // 120 BPM, quarter = 500ms
        if (*p == '.') dur = dur * 3 / 2;
        notes[count].freqHz = isRest ? 0 : noteFreq(semi, octave);
        notes[count].durMs  = (uint16_t)(dur > 65535u ? 65535u : dur);
        count++;
        tok = strtok_r(nullptr, " ", &sp);
    }
    return count;
}

// ---------------------------------------------------------------------------
// Server callbacks
// ---------------------------------------------------------------------------

class BleServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer*) override {
        if (s_state) s_state->bleConnected = true;
    }
    void onDisconnect(BLEServer*) override {
        if (s_state) {
            s_state->bleConnected = false;
            s_state->bleClientWantsNewline = false;
            s_state->streamEnabled = false;
        }
    }
};

// ---------------------------------------------------------------------------
// Command characteristic callbacks — runs on BLE FreeRTOS task
// ---------------------------------------------------------------------------

static const char* const kHelpLines[] = {
    "PING",
    "GET_TILT",
    "CALIBRATE [gx gy gz]",
    "CALIBRATE_RESET",
    "GET_STATUS",
    "GET_TIME",
    "GET_RADEC",
    "GET_ALTAZ",
    "GET_MSG",
    "SET_TIME <ISO8601> [<tz>]",
    "SET_SIDEREAL_TIME <HH:MM:SS> [<label>]",
    "SET_RADEC <ra> <dec>",
    "SET_ALTAZ <alt> <az>",
    "SHOW_MSG <dur> [FONT:<n>] [BEEP] <text...>",
    "SHOW_MSG_WAIT <dur> <btns> [FONT:<n>] [BEEP] <text...>",
    "  FONT: 1=small 2=med(def) 3=dvu18 4=dvu24 5=goth16 6=goth24",
    "  FONT 1-4: ASCII only; 5-6 (U8g2 gothic): Latin-1 accents OK",
    "CANCEL_MSG",
    "START_STREAM <ms>",
    "STOP_STREAM",
    "SET_NIGHT_MODE ON|OFF",
    "BEEP [<notes...>]",
    "HELP",
};
static const int kHelpLineCount = (int)(sizeof(kHelpLines) / sizeof(kHelpLines[0]));

class BleCmdCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pChar) override {
        if (!s_state) return;

        // Copy value to local buffer (pChar->getValue() is a std::string)
        std::string val = pChar->getValue();
        if (val.empty()) return;

        char cmd[256];
        size_t copyLen = val.size() < sizeof(cmd) - 1 ? val.size() : sizeof(cmd) - 1;
        memcpy(cmd, val.data(), copyLen);
        cmd[copyLen] = '\0';

        // Detect newline-terminated protocol (sticky per connection)
        if (!s_state->bleClientWantsNewline && val.back() == '\n')
            s_state->bleClientWantsNewline = true;

        // Strip trailing whitespace/newline
        int end = (int)strlen(cmd) - 1;
        while (end >= 0 && (cmd[end] == '\r' || cmd[end] == '\n' || cmd[end] == ' '))
            cmd[end--] = '\0';

        char resp[160];
        resp[0] = '\0';

        // Tokenize
        char* saveptr = nullptr;
        char* tok = strtok_r(cmd, " ", &saveptr);
        if (!tok) {
            strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1);
            goto respond;
        }

        // ---- Query commands ----

        if (strcasecmp(tok, "PING") == 0) {
            strncpy(resp, "OK PONG", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "GET_TILT") == 0) {
            snprintf(resp, sizeof(resp), "TILT %+.2f %+.2f",
                     s_state->pitchDeg, s_state->rollDeg);

        } else if (strcasecmp(tok, "GET_STATUS") == 0) {
            buildStatusLine(*s_state, resp, sizeof(resp));

        } else if (strcasecmp(tok, "GET_TIME") == 0) {
            time_t t = deviceCurrentTime(*s_state);
            if (t == 0) {
                strncpy(resp, "TIME NONE", sizeof(resp) - 1);
            } else {
                char iso[24];
                formatIso8601(t, iso, sizeof(iso));
                snprintf(resp, sizeof(resp), "TIME %s", iso);
            }

        } else if (strcasecmp(tok, "GET_RADEC") == 0) {
            snprintf(resp, sizeof(resp), "RADEC %s %s",
                     s_state->raText, s_state->decText);

        } else if (strcasecmp(tok, "GET_ALTAZ") == 0) {
            snprintf(resp, sizeof(resp), "ALTAZ %s %s",
                     s_state->altText, s_state->azText);

        } else if (strcasecmp(tok, "GET_MSG") == 0) {
            if (!s_state->messageActive) {
                strncpy(resp, "MSG NONE", sizeof(resp) - 1);
            } else {
                char durStr[12];
                if (s_state->messagePersistent) {
                    strncpy(durStr, "INF", sizeof(durStr) - 1);
                } else {
                    uint32_t now = millis();
                    int remaining = 0;
                    if (s_state->messageExpiresAtMs > now)
                        remaining = (int)((s_state->messageExpiresAtMs - now) / 1000) + 1;
                    snprintf(durStr, sizeof(durStr), "%d", remaining);
                }
                // Build button string
                char btnStr[16] = "NONE";
                if (s_state->messageAwaitButtons) {
                    btnStr[0] = '\0';
                    bool first = true;
                    if (s_state->messageAwaitButtons & BTN_MASK_M5) {
                        strcat(btnStr, "M5"); first = false;
                    }
                    if (s_state->messageAwaitButtons & BTN_MASK_A) {
                        if (!first) strcat(btnStr, ",");
                        strcat(btnStr, "A"); first = false;
                    }
                    if (s_state->messageAwaitButtons & BTN_MASK_B) {
                        if (!first) strcat(btnStr, ",");
                        strcat(btnStr, "B");
                    }
                }
                snprintf(resp, sizeof(resp), "MSG ACTIVE %s BUTTONS=%s TEXT=%s",
                         durStr, btnStr, s_state->messageText);
            }

        // ---- Update commands ----

        } else if (strcasecmp(tok, "SET_TIME") == 0) {
            char* iso = strtok_r(nullptr, " ", &saveptr);
            if (!iso) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            time_t t;
            char tzBuf[16] = {};
            if (!parseIso8601(iso, &t, tzBuf, sizeof(tzBuf))) {
                strncpy(resp, "ERR BAD_TIME", sizeof(resp) - 1);
            } else {
                if (tzBuf[0] == '\0') {
                    char* tzTok = strtok_r(nullptr, " ", &saveptr);
                    if (tzTok) snprintf(tzBuf, sizeof(tzBuf), "%s", tzTok);
                }
                s_state->timeEpochSec    = t;
                s_state->timeSetAtMillis = millis();
                s_state->siderealMode    = false;
                strncpy(s_state->timezoneLabel, tzBuf, sizeof(s_state->timezoneLabel) - 1);
                s_state->timezoneLabel[sizeof(s_state->timezoneLabel) - 1] = '\0';
                strncpy(resp, "OK TIME", sizeof(resp) - 1);
            }

        } else if (strcasecmp(tok, "SET_SIDEREAL_TIME") == 0) {
            char* hms = strtok_r(nullptr, " ", &saveptr);
            if (!hms) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            time_t t;
            if (!parseSiderealHMS(hms, &t)) {
                strncpy(resp, "ERR BAD_TIME", sizeof(resp) - 1);
            } else {
                char* labelTok = strtok_r(nullptr, " ", &saveptr);
                s_state->timeEpochSec    = t;
                s_state->timeSetAtMillis = millis();
                s_state->siderealMode    = true;
                const char* label = (labelTok && labelTok[0]) ? labelTok : "LST";
                strncpy(s_state->timezoneLabel, label, sizeof(s_state->timezoneLabel) - 1);
                s_state->timezoneLabel[sizeof(s_state->timezoneLabel) - 1] = '\0';
                strncpy(resp, "OK SIDEREAL", sizeof(resp) - 1);
            }

        } else if (strcasecmp(tok, "SET_RADEC") == 0) {
            char* ra  = strtok_r(nullptr, " ", &saveptr);
            char* dec = strtok_r(nullptr, " ", &saveptr);
            if (!ra || !dec) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            strncpy(s_state->raText,  ra,  sizeof(s_state->raText)  - 1);
            strncpy(s_state->decText, dec, sizeof(s_state->decText) - 1);
            strncpy(resp, "OK RADEC", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "SET_ALTAZ") == 0) {
            char* alt = strtok_r(nullptr, " ", &saveptr);
            char* az  = strtok_r(nullptr, " ", &saveptr);
            if (!alt || !az) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            strncpy(s_state->altText, alt, sizeof(s_state->altText) - 1);
            strncpy(s_state->azText,  az,  sizeof(s_state->azText)  - 1);
            strncpy(resp, "OK ALTAZ", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "SHOW_MSG") == 0) {
            char* dur  = strtok_r(nullptr, " ", &saveptr);
            // Everything remaining after duration is the message text
            char* text = strtok_r(nullptr, "", &saveptr);
            if (!dur || !text) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            while (*text == ' ') text++;
            {
                uint8_t fontCode = 0;
                bool beep = false;
                while (*text) {
                    if (strncasecmp(text, "FONT:", 5) == 0) {
                        fontCode = (uint8_t)atoi(text + 5);
                        while (*text && *text != ' ') text++;
                        while (*text == ' ') text++;
                    } else if (strncasecmp(text, "BEEP", 4) == 0 && (text[4]==' ' || text[4]=='\0')) {
                        beep = true;
                        text += 4;
                        while (*text == ' ') text++;
                    } else {
                        break;
                    }
                }
                s_state->messageFontCode = fontCode;
                if (beep) {
                    s_state->melodyNotes[0].freqHz = 880;
                    s_state->melodyNotes[0].durMs  = 200;
                    s_state->melodyPendingLength   = 1;
                    s_state->melodyPending         = true;
                }
            }
            strncpy(s_state->messageText, text, sizeof(s_state->messageText) - 1);
            s_state->messageText[sizeof(s_state->messageText) - 1] = '\0';
            s_state->messageAwaitButtons = 0;
            if (strcasecmp(dur, "INF") == 0) {
                s_state->messagePersistent   = true;
                s_state->messageExpiresAtMs  = 0;
            } else {
                int secs = atoi(dur);
                s_state->messagePersistent   = false;
                s_state->messageExpiresAtMs  = millis() + (uint32_t)(secs * 1000);
            }
            if (s_state->screenIndex != SCREEN_MESSAGE)
                s_state->prevScreenIndex = s_state->screenIndex;
            s_state->messageActive   = true;
            s_state->screenIndex     = SCREEN_MESSAGE;
            strncpy(resp, "OK MSG", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "SHOW_MSG_WAIT") == 0) {
            char* dur  = strtok_r(nullptr, " ", &saveptr);
            char* btns = strtok_r(nullptr, " ", &saveptr);
            char* text = strtok_r(nullptr, "", &saveptr);
            if (!dur || !btns || !text) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            while (*text == ' ') text++;
            {
                uint8_t fontCode = 0;
                bool beep = false;
                while (*text) {
                    if (strncasecmp(text, "FONT:", 5) == 0) {
                        fontCode = (uint8_t)atoi(text + 5);
                        while (*text && *text != ' ') text++;
                        while (*text == ' ') text++;
                    } else if (strncasecmp(text, "BEEP", 4) == 0 && (text[4]==' ' || text[4]=='\0')) {
                        beep = true;
                        text += 4;
                        while (*text == ' ') text++;
                    } else {
                        break;
                    }
                }
                s_state->messageFontCode = fontCode;
                if (beep) {
                    s_state->melodyNotes[0].freqHz = 880;
                    s_state->melodyNotes[0].durMs  = 200;
                    s_state->melodyPendingLength   = 1;
                    s_state->melodyPending         = true;
                }
            }
            strncpy(s_state->messageText, text, sizeof(s_state->messageText) - 1);
            s_state->messageText[sizeof(s_state->messageText) - 1] = '\0';
            s_state->messageAwaitButtons = parseMsgButtons(btns);
            if (strcasecmp(dur, "INF") == 0) {
                s_state->messagePersistent   = true;
                s_state->messageExpiresAtMs  = 0;
            } else {
                int secs = atoi(dur);
                s_state->messagePersistent   = false;
                s_state->messageExpiresAtMs  = millis() + (uint32_t)(secs * 1000);
            }
            if (s_state->screenIndex != SCREEN_MESSAGE)
                s_state->prevScreenIndex = s_state->screenIndex;
            s_state->messageActive   = true;
            s_state->screenIndex     = SCREEN_MESSAGE;
            strncpy(resp, "OK MSG_WAIT", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "CANCEL_MSG") == 0) {
            s_state->messageActive = false;
            s_state->screenIndex   = s_state->prevScreenIndex;
            strncpy(resp, "OK MSG_CANCEL", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "START_STREAM") == 0) {
            char* ms = strtok_r(nullptr, " ", &saveptr);
            if (!ms) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            uint32_t period = (uint32_t)atoi(ms);
            if (period < 100) period = 100; // minimum 100ms
            s_state->streamEnabled  = true;
            s_state->streamPeriodMs = period;
            s_state->lastStreamMs   = millis();
            snprintf(resp, sizeof(resp), "OK STREAM %u", period);

        } else if (strcasecmp(tok, "STOP_STREAM") == 0) {
            s_state->streamEnabled = false;
            strncpy(resp, "OK STREAM 0", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "SET_NIGHT_MODE") == 0) {
            char* val = strtok_r(nullptr, " ", &saveptr);
            if (!val) { strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1); goto respond; }
            if (strcasecmp(val, "ON") == 0) {
                s_state->nightMode = true;
                strncpy(resp, "OK NIGHT_MODE ON", sizeof(resp) - 1);
            } else if (strcasecmp(val, "OFF") == 0) {
                s_state->nightMode = false;
                strncpy(resp, "OK NIGHT_MODE OFF", sizeof(resp) - 1);
            } else {
                strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1);
            }

        } else if (strcasecmp(tok, "BEEP") == 0) {
            char* arg = strtok_r(nullptr, "", &saveptr);
            while (arg && *arg == ' ') arg++;
            if (!arg || *arg == '\0') {
                s_state->melodyNotes[0] = {880, 200};
                s_state->melodyPendingLength = 1;
            } else {
                int errPos = 0;
                int n = parseMelody(arg, (MelodyNote*)s_state->melodyNotes, MELODY_MAX_NOTES, &errPos);
                if (n <= 0) { snprintf(resp, sizeof(resp), "BAD MELODY @%d", errPos); goto respond; }
                s_state->melodyPendingLength = n;
            }
            s_state->melodyPending = true;
            strncpy(resp, "OK BEEP", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "CALIBRATE") == 0) {
            float rgx = 0.0f, rgy = 0.0f, rgz = 1.0f;
            char* sx = strtok_r(nullptr, " ", &saveptr);
            if (sx) {
                char* sy = strtok_r(nullptr, " ", &saveptr);
                char* sz = sy ? strtok_r(nullptr, " ", &saveptr) : nullptr;
                if (!sy || !sz) {
                    strncpy(resp, "ERR BAD_ARGS", sizeof(resp) - 1);
                    goto respond;
                }
                if (s_imu) s_imu->calibrateFrom(strtof(sx, nullptr),
                                                 strtof(sy, nullptr),
                                                 strtof(sz, nullptr));
                if (s_imu) s_imu->getCalibrationRef(rgx, rgy, rgz);
            } else {
                if (s_imu) s_imu->calibrate(rgx, rgy, rgz);
            }
            snprintf(resp, sizeof(resp), "CALIBRATED %+.4f %+.4f %+.4f", rgx, rgy, rgz);

        } else if (strcasecmp(tok, "CALIBRATE_RESET") == 0) {
            if (s_imu) s_imu->resetCalibration();
            strncpy(resp, "OK CALIBRATION_RESET", sizeof(resp) - 1);

        } else if (strcasecmp(tok, "HELP") == 0 || strcasecmp(tok, "?") == 0) {
            s_state->pendingBleHelpReady = true;
            return;

        } else {
            strncpy(resp, "ERR UNKNOWN_COMMAND", sizeof(resp) - 1);
        }

    respond:
        // Hand off response to main loop via volatile buffer
        strncpy((char*)s_state->pendingBleResponse, resp,
                sizeof(s_state->pendingBleResponse) - 1);
        ((char*)s_state->pendingBleResponse)[sizeof(s_state->pendingBleResponse) - 1] = '\0';
        s_state->pendingBleResponseReady = true;
    }
};

// ---------------------------------------------------------------------------
// BleManager
// ---------------------------------------------------------------------------

void BleManager::begin(DeviceState* state, ImuManager* imu) {
    s_state = state;
    s_imu   = imu;

    // Ensure mktime interprets struct tm as UTC
    setenv("TZ", "UTC0", 1);
    tzset();

    BLEDevice::setMTU(185);
    BLEDevice::init(BLE_DEVICE_NAME);

    _pServer = BLEDevice::createServer();
    _pServer->setCallbacks(new BleServerCallbacks());

    BLEService* pService = _pServer->createService(BLE_SERVICE_UUID);

    // Response characteristic: READ + NOTIFY
    _pRespChar = pService->createCharacteristic(
        BLE_RESP_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    _pRespChar->addDescriptor(new BLE2902());

    // Command characteristic: WRITE + WRITE_NR
    BLECharacteristic* pCmdChar = pService->createCharacteristic(
        BLE_CMD_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    pCmdChar->setCallbacks(new BleCmdCallbacks());

    // Status characteristic: READ only
    _pStatusChar = pService->createCharacteristic(
        BLE_STATUS_UUID,
        BLECharacteristic::PROPERTY_READ);
    _pStatusChar->setValue("STATUS SCREEN=CLINOMETER BLE=0 STREAM=0 BAT=0.00");

    // Keep s_pRespChar accessible to future notification helpers if needed
    s_pRespChar = _pRespChar;

    pService->start();
    _pServer->getAdvertising()->start();
}

void BleManager::update(DeviceState& state) {
    // Restart advertising after disconnect
    if (_wasConnected && !state.bleConnected) {
        _pServer->startAdvertising();
    }
    _wasConnected = state.bleConnected;

    // Drain pending command response
    if (state.pendingBleResponseReady) {
        sendResponse((const char*)state.pendingBleResponse);
        state.pendingBleResponseReady = false;
    }

    // Drain pending HELP response (one burst of notifications)
    if (state.pendingBleHelpReady) {
        for (int i = 0; i < kHelpLineCount; i++)
            sendResponse(kHelpLines[i]);
        sendResponse("OK");
        state.pendingBleHelpReady = false;
    }

    // Drain pending button event
    if (state.pendingBleEventReady) {
        sendEvent((const char*)state.pendingBleEvent);
        state.pendingBleEventReady = false;
    }

    // Notify on screen change
    if (state.screenIndex != _lastScreenIndex) {
        _lastScreenIndex = state.screenIndex;
        if (state.bleConnected) {
            char buf[48];
            snprintf(buf, sizeof(buf), "EVENT SCREEN %s", screenName(state.screenIndex));
            sendEvent(buf);
        }
    }

    // Optional tilt streaming
    if (state.streamEnabled && state.bleConnected) {
        uint32_t now = millis();
        if ((now - state.lastStreamMs) >= state.streamPeriodMs) {
            char buf[64];
            snprintf(buf, sizeof(buf), "TILT %+.2f %+.2f",
                     state.pitchDeg, state.rollDeg);
            sendResponse(buf);
            state.lastStreamMs = now;
        }
    }

    // Update status characteristic every ~2 s (no notify, just READ value)
    uint32_t now = millis();
    if ((now - _lastStatusMs) >= 2000) {
        _lastStatusMs = now;
        _updateStatusChar(state);
    }
}

void BleManager::sendResponse(const char* msg) {
    if (!_pRespChar || !msg) return;
    if (s_state && s_state->bleClientWantsNewline) {
        char buf[162]; // max pendingBleResponse (160) + '\n' + '\0'
        snprintf(buf, sizeof(buf), "%s\n", msg);
        _pRespChar->setValue((uint8_t*)buf, strlen(buf));
    } else {
        _pRespChar->setValue((uint8_t*)msg, strlen(msg));
    }
    _pRespChar->notify();
}

void BleManager::sendEvent(const char* msg) {
    sendResponse(msg); // both go on the same response/notify characteristic
}

void BleManager::_updateStatusChar(const DeviceState& state) {
    if (!_pStatusChar) return;
    char buf[80];
    snprintf(buf, sizeof(buf), "SCREEN=%s;BLE=%d;BAT=%.2f;STREAM=%d",
             screenName(state.screenIndex),
             state.bleConnected ? 1 : 0,
             state.batteryVoltage,
             state.streamEnabled ? 1 : 0);
    _pStatusChar->setValue(buf);
}
