#include "Display.h"
#include <math.h>
#include <time.h>

void Display::begin() {
    M5.Display.setRotation(1);
    M5.Display.setBrightness(128);
    _W = M5.Display.width();
    _H = M5.Display.height();
    _sprite = new LGFX_Sprite(&M5.Display);
    _sprite->setColorDepth(8);
    _sprite->createSprite(_W, _H);
}

void Display::setBrightness(uint8_t val) {
    M5.Display.setBrightness(val);
}

void Display::update(const DeviceState& state) {
    uint32_t now = millis();
    uint32_t interval = (state.screenIndex == SCREEN_CLINOMETER ||
                         state.screenIndex == SCREEN_MESSAGE) ? 100 : 200;
    if ((now - _lastRefreshMs) < interval) return;
    _lastRefreshMs = now;

    // Auto-rotate 180° based on gravity. Hysteresis at ±0.3 g prevents flicker.
    // M5StickC Plus 2 (IMU_LONG_AXIS_IS_Y=1): long axis is Y, so gravX signals
    // which end is up. Other devices (IMU_LONG_AXIS_IS_Y=0): long axis is X, so
    // gravY signals orientation.
    if (state.imuAvailable) {
#if IMU_LONG_AXIS_IS_Y
        float flipSensor = state.gravX;
#else
        float flipSensor = state.gravY;
#endif
        if (!_screenFlipped && flipSensor < -0.3f) {
            _screenFlipped = true;
            M5.Display.setRotation(3);
        } else if (_screenFlipped && flipSensor > 0.3f) {
            _screenFlipped = false;
            M5.Display.setRotation(1);
        }
    }

    _sprite->fillScreen(TFT_BLACK);

    switch (state.screenIndex) {
        case SCREEN_CLINOMETER: _drawClinometer(state); break;
        case SCREEN_TIME:       _drawTime(state);       break;
        case SCREEN_RADEC:      _drawRADec(state);      break;
        case SCREEN_ALTAZ:      _drawAltAz(state);      break;
        case SCREEN_BATTERY:    _drawBattery(state);    break;
        case SCREEN_MESSAGE:    _drawMessage(state);    break;
        default: break;
    }

    _drawBleIndicator(state.bleConnected, state.nightMode);
    _flush();
}

// Format a degree value into at most 6 characters: "+99.99" or "+100.0"
static void fmtAngle(char* buf, size_t sz, float deg) {
    snprintf(buf, sz, fabsf(deg) < 100.0f ? "%+.2f" : "%+.1f", deg);
}

// --- Screen renderers ---

void Display::_drawClinometer(const DeviceState& state) {
    bool n = state.nightMode;
    int cx   = _W / 3;
    int cy   = _H / 2;
    int maxR = (cx < cy ? cx : cy) - 12;

    // Crosshairs
    _sprite->drawLine(cx, cy - maxR, cx, cy + maxR, _c(TFT_DARKGREY, n));
    _sprite->drawLine(cx - maxR, cy, cx + maxR, cy, _c(TFT_DARKGREY, n));

    // Concentric circles for 1°, 2°, 3°
    for (int deg = 1; deg <= 3; deg++) {
        int r = deg * maxR / 3;
        uint16_t col = (deg == 1) ? _c(TFT_GREEN, n) : (deg == 2) ? _c(TFT_YELLOW, n) : _c(TFT_RED, n);
        _sprite->drawCircle(cx, cy, r, col);
    }

    if (!state.imuAvailable) {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString("IMU N/A", cx, cy);
        _sprite->setTextDatum(textdatum_t::top_left);
        return;
    }

    // Bubble position: use sin so the bubble re-centres at ±180° (upside-down level).
    // Scale so sin(3°) == maxR, matching the concentric-circle graduations.
    static const float kDeg2Rad  = 0.017453293f;
    static const float kSin3     = 0.052335956f; // sinf(3°)
    float bubbleScale = (float)maxR / kSin3;
    int bx = cx - (int)(sinf(state.rollDeg  * kDeg2Rad) * bubbleScale);
    int by = cy + (int)(sinf(state.pitchDeg * kDeg2Rad) * bubbleScale);
    bx = constrain(bx, cx - maxR, cx + maxR);
    by = constrain(by, cy - maxR, cy + maxR);
    int dotR = maxR / 9;
    if (dotR < 4) dotR = 4;
    _sprite->fillCircle(bx, by, dotR, _c(TFT_WHITE, n));
    _sprite->drawCircle(bx, by, dotR, _c(TFT_YELLOW, n));

    // Numeric readout — right panel
    char abuf[8];
    int px = cx + maxR + 20;
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H *  8 / 135);
    _sprite->print("Pitch");
    _sprite->setFont(&fonts::Font4);
    _sprite->setCursor(px, _H * 22 / 135);
    fmtAngle(abuf, sizeof(abuf), state.pitchDeg);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(px, _H * 68 / 135);
    _sprite->print("Roll");
    _sprite->setFont(&fonts::Font4);
    _sprite->setCursor(px, _H * 82 / 135);
    fmtAngle(abuf, sizeof(abuf), state.rollDeg);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::Font0);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(px, _H * 118 / 135);
    _sprite->print("degrees");
}

void Display::_drawTime(const DeviceState& state) {
    bool n = state.nightMode;
    int cx = _W / 2;
    time_t t = deviceCurrentTime(state);
    if (t == 0) {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString("NO TIME SET", cx, _H / 2);
        _sprite->setTextDatum(textdatum_t::top_left);
        return;
    }

    struct tm ti;
    gmtime_r(&t, &ti);

    // Timezone label top-left (prominent, above clock)
    if (state.timezoneLabel[0] != '\0') {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_CYAN, n));
        _sprite->setTextDatum(textdatum_t::top_left);
        _sprite->drawString(state.timezoneLabel, 10, 5);
    }

    // Time: HH:MM:SS large centered
    char timeBuf[12];
    snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d:%02d",
             ti.tm_hour, ti.tm_min, ti.tm_sec);
    _sprite->setFont(&fonts::Font7);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setTextDatum(textdatum_t::middle_center);
    _sprite->drawString(timeBuf, cx, _H * 62 / 135);

    _sprite->setFont(&fonts::Font2);
    if (state.siderealMode) {
        _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
        const char* lbl = state.timezoneLabel[0] ? state.timezoneLabel : "LST";
        _sprite->drawString(lbl, cx, _H * 105 / 135);
    } else {
        char dateBuf[12];
        snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday);
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
        _sprite->drawString(dateBuf, cx, _H * 105 / 135);
    }
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawRADec(const DeviceState& state) {
    bool n = state.nightMode;
    int mx = _W / 24;   // ≈10px left margin at W=240
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(mx, _H * 10 / 135);
    _sprite->print("RA");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 28 / 135);
    _sprite->print(state.raText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(mx, _H * 72 / 135);
    _sprite->print("Dec");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 90 / 135);
    _sprite->print(state.decText);
}

void Display::_drawAltAz(const DeviceState& state) {
    bool n = state.nightMode;
    int mx = _W / 24;
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(mx, _H * 10 / 135);
    _sprite->print("Alt");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 28 / 135);
    _sprite->print(state.altText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(mx, _H * 72 / 135);
    _sprite->print("Az");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 90 / 135);
    _sprite->print(state.azText);
}

// Font coverage:
//   Font2, Font4, DejaVu*: ASCII 0x20-0x7E only — no accented characters.
//   Font6/Font8 are 7-segment digit-only glyphs; do not use for text.
//   lgfxJapanGothic (U8g2) covers full Unicode including Latin-1 extended
//   (é, ü, ñ …) — use codes 5 or 6 whenever accented characters are needed.
static void utf8TrimTail(char* s) {
    int len = (int)strlen(s);
    if (len == 0) return;
    int i = len - 1;
    while (i >= 0 && ((uint8_t)s[i] & 0xC0) == 0x80) i--;
    if (i < 0) return;
    uint8_t lead = (uint8_t)s[i];
    int expected = (lead < 0x80) ? 1 : (lead < 0xE0) ? 2 : (lead < 0xF0) ? 3 : 4;
    if (len - i < expected) s[i] = '\0';
}

static const char* utf8Next(const char* p) {
    uint8_t c = (uint8_t)*p;
    if (c < 0x80) return p + 1;
    if (c < 0xE0) return p + 2;
    if (c < 0xF0) return p + 3;
    return p + 4;
}

static const lgfx::IFont* _msgFont(uint8_t code) {
    switch (code) {
        case 1:  return &fonts::Font2;              //  16 px, ASCII only
        case 3:  return &fonts::DejaVu18;           // ~18 px, ASCII only
        case 4:  return &fonts::DejaVu24;           // ~24 px, ASCII only
        case 5:  return &fonts::lgfxJapanGothic_16; //  16 px, Unicode (Latin-1 accents OK)
        case 6:  return &fonts::lgfxJapanGothic_24; //  24 px, Unicode (Latin-1 accents OK)
        default: return &fonts::Font4;              //  26 px, ASCII only (codes 0, 2, unknown)
    }
}

void Display::_drawMessage(const DeviceState& state) {
    if (!state.messageActive) return;
    bool n = state.nightMode;

    // Countdown top-right (if timed)
    if (!state.messagePersistent && state.messageExpiresAtMs > 0) {
        uint32_t now = millis();
        int remaining = 0;
        if (state.messageExpiresAtMs > now) {
            remaining = (int)((state.messageExpiresAtMs - now) / 1000) + 1;
        }
        char countdown[8];
        snprintf(countdown, sizeof(countdown), "%ds", remaining);
        _sprite->setFont(&fonts::Font2);
        _sprite->setTextColor(_c(TFT_YELLOW, n));
        _sprite->setTextDatum(textdatum_t::top_right);
        _sprite->drawString(countdown, _W - 30, 4);
        _sprite->setTextDatum(textdatum_t::top_left);
    }

    _sprite->setFont(_msgFont(state.messageFontCode));
    const int lineH   = _sprite->fontHeight() + 2;
    const int maxW    = _W - 8;  // 4 px margin each side
    const int startY  = _H * 20 / 135;
    const int bottomY = (state.messageAwaitButtons != 0) ? (_H - lineH - 2) : (_H - 2);

    _sprite->setTextColor(_c(TFT_WHITE, n));

    const char* p = state.messageText;
    int y = startY;

    while (*p && y + lineH <= bottomY) {
        char line[128] = "";

        while (*p) {
            const char* wEnd = p;
            while (*wEnd && *wEnd != ' ') wEnd++;

            char cand[128];
            if (line[0] == '\0')
                snprintf(cand, sizeof(cand), "%.*s", (int)(wEnd - p), p);
            else
                snprintf(cand, sizeof(cand), "%s %.*s", line, (int)(wEnd - p), p);
            utf8TrimTail(cand);

            if (_sprite->textWidth(cand) <= maxW) {
                strncpy(line, cand, sizeof(line) - 1);
                p = wEnd;
                if (*p == ' ') p++;
            } else if (line[0] != '\0') {
                break;  // word doesn't fit but line has content — emit line
            } else {
                // Word alone is too wide: split character by character
                while (*p && *p != ' ') {
                    const char* cNext = utf8Next(p);
                    snprintf(cand, sizeof(cand), "%s%.*s", line, (int)(cNext - p), p);
                    utf8TrimTail(cand);
                    if (_sprite->textWidth(cand) > maxW) {
                        if (line[0] == '\0') { strncpy(line, cand, sizeof(line)-1); p = cNext; }
                        break;
                    }
                    strncpy(line, cand, sizeof(line) - 1);
                    p = cNext;
                }
                break;  // emit whatever was built
            }
        }

        if (line[0] != '\0') {
            _sprite->setTextDatum(textdatum_t::top_center);
            _sprite->drawString(line, _W / 2, y);
            y += lineH;
        }
    }
    _sprite->setTextDatum(textdatum_t::top_left);

    // Button hint at bottom
    if (state.messageAwaitButtons != 0) {
        char hint[32] = "[ ";
        bool first = true;
        if (state.messageAwaitButtons & BTN_MASK_M5) {
            strcat(hint, "M5"); first = false;
        }
        if (state.messageAwaitButtons & BTN_MASK_A) {
            if (!first) strcat(hint, ",");
            strcat(hint, "A"); first = false;
        }
        if (state.messageAwaitButtons & BTN_MASK_B) {
            if (!first) strcat(hint, ",");
            strcat(hint, "B");
        }
        strcat(hint, " ]");
        _sprite->setFont(&fonts::Font2);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->setTextDatum(textdatum_t::bottom_center);
        _sprite->drawString(hint, _W / 2, _H - 2);
        _sprite->setTextDatum(textdatum_t::top_left);
    }
}

void Display::_drawBattery(const DeviceState& state) {
    bool n = state.nightMode;
    int pct = state.batteryLevel;

    // Title
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setTextDatum(textdatum_t::top_center);
    _sprite->drawString("BATTERY", _W / 2, _H * 8 / 135);
    _sprite->setTextDatum(textdatum_t::top_left);

    // Bar geometry
    const int BAR_X = _W * 18 / 240;
    const int BAR_Y = _H * 36 / 135;
    const int BAR_W = _W * 192 / 240;
    const int BAR_H = _H * 28 / 135;
    const int TIP_H = BAR_H / 2;
    const int TIP_W = _W * 7 / 240 > 4 ? _W * 7 / 240 : 5;

    // Battery body outline
    _sprite->drawRect(BAR_X, BAR_Y, BAR_W, BAR_H, _c(TFT_DARKGREY, n));
    // Positive terminal nub on the right
    _sprite->fillRect(BAR_X + BAR_W, BAR_Y + (BAR_H - TIP_H) / 2, TIP_W, TIP_H, _c(TFT_DARKGREY, n));

    // Fill colour based on level
    uint16_t fillColor;
    if      (pct < 0)   fillColor = _c(TFT_DARKGREY, n);
    else if (pct <= 20) fillColor = _c(TFT_RED, n);
    else if (pct <= 50) fillColor = _c(TFT_YELLOW, n);
    else                fillColor = _c(TFT_GREEN, n);

    int fillW = (pct >= 0) ? (int)((float)pct / 100.0f * (BAR_W - 4)) : 0;
    if (fillW > 0) {
        _sprite->fillRect(BAR_X + 2, BAR_Y + 2, fillW, BAR_H - 4, fillColor);
    }

    // Voltage and percentage below the bar, positioned relative to it
    int readY = _H * 92 / 135;
    int voltX = BAR_X + BAR_W * 3 / 8;
    int pctX  = BAR_X + BAR_W * 7 / 8;

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setTextDatum(textdatum_t::middle_center);
    if (state.batteryVoltage > 0.5f) {
        char voltBuf[12];
        snprintf(voltBuf, sizeof(voltBuf), "%.2f V", state.batteryVoltage);
        _sprite->drawString(voltBuf, voltX, readY);
    } else {
        _sprite->drawString("-- V", voltX, readY);
    }

    if (pct >= 0) {
        char pctBuf[8];
        snprintf(pctBuf, sizeof(pctBuf), "%d%%", pct);
        _sprite->drawString(pctBuf, pctX, readY);
    } else {
        _sprite->drawString("--%", pctX, readY);
    }
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawBleIndicator(bool connected, bool nightMode) {
    uint16_t col = connected ? _c(TFT_GREEN, nightMode) : _c(0x4208, nightMode);
    _sprite->fillCircle(_W - 12, 8, 5, col);
}

void Display::_flush() {
    _sprite->pushSprite(0, 0);
}

uint16_t Display::_c(uint16_t color, bool night) const {
    if (!night || color == TFT_BLACK) return color;
    if (color == TFT_GREEN) return 0xFB00u; // warm orange-red accent in RGB565
    return TFT_RED;
}
