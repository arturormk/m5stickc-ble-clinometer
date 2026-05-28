#include "Display.h"
#include <math.h>
#include <time.h>

void Display::begin() {
    bool isStickC = (M5.getBoard() == m5::board_t::board_M5StickCPlus2
                  || M5.getBoard() == m5::board_t::board_M5StickCPlus);
    M5.Display.setRotation(isStickC ? 3 : 1);
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

// ↕ icon: horizontal pivot bar + vertical double-arrow
static void _drawVertIcon(LGFX_Sprite* spr, int cx, int cy, uint16_t col) {
    spr->drawLine(cx - 7, cy,     cx + 7, cy,     col);
    spr->drawLine(cx,     cy - 1, cx,     cy - 5, col);
    spr->drawLine(cx,     cy - 7, cx - 3, cy - 4, col);
    spr->drawLine(cx,     cy - 7, cx + 3, cy - 4, col);
    spr->drawLine(cx,     cy + 1, cx,     cy + 5, col);
    spr->drawLine(cx,     cy + 7, cx - 3, cy + 4, col);
    spr->drawLine(cx,     cy + 7, cx + 3, cy + 4, col);
}

// ↔ icon: vertical pivot bar + horizontal double-arrow
static void _drawHorizIcon(LGFX_Sprite* spr, int cx, int cy, uint16_t col) {
    spr->drawLine(cx,     cy - 7, cx,     cy + 7, col);
    spr->drawLine(cx - 1, cy,     cx - 5, cy,     col);
    spr->drawLine(cx - 7, cy,     cx - 4, cy - 3, col);
    spr->drawLine(cx - 7, cy,     cx - 4, cy + 3, col);
    spr->drawLine(cx + 1, cy,     cx + 5, cy,     col);
    spr->drawLine(cx + 7, cy,     cx + 4, cy - 3, col);
    spr->drawLine(cx + 7, cy,     cx + 4, cy + 3, col);
}

void Display::_drawClinometer(const DeviceState& state) {
    bool n = state.nightMode;

    static constexpr float DISP_ALPHA = 0.3f;
    _dispPitch   = DISP_ALPHA * state.pitchDeg   + (1.0f - DISP_ALPHA) * _dispPitch;
    _dispRoll    = DISP_ALPHA * state.rollDeg    + (1.0f - DISP_ALPHA) * _dispRoll;
    _dispUxPitch = DISP_ALPHA * state.uxPitchDeg + (1.0f - DISP_ALPHA) * _dispUxPitch;
    _dispUxRoll  = DISP_ALPHA * state.uxRollDeg  + (1.0f - DISP_ALPHA) * _dispUxRoll;

    int cx   = _W / 3;
    int cy   = _H / 2;
    int maxR = (cx < cy ? cx : cy) - 12;

    // YX layout: pitch is a Y-type axis (|code|==2) and roll is X-type (|code|==1).
    // In that case the crosshair colours and double-arrow icons swap so the colour
    // always tracks the axis type that matches the crosshair orientation.
    bool yx = (abs((int)state.pitchAxis) == 2 && abs((int)state.rollAxis) == 1);
    // vertAxis  = the axis shown by the vertical   crosshair (drives vertical   tilt)
    // horizAxis = the axis shown by the horizontal crosshair (drives horizontal tilt)
    int8_t  vertAxis  = yx ? state.rollAxis  : state.pitchAxis;
    int8_t  horizAxis = yx ? state.pitchAxis : state.rollAxis;
    uint16_t vertCol  = _c(yx ? TFT_ORANGE : TFT_CYAN,   n);
    uint16_t horizCol = _c(yx ? TFT_CYAN   : TFT_ORANGE, n);

    // Crosshair lines
    _sprite->drawLine(cx, cy - maxR, cx, cy + maxR, vertCol);
    _sprite->drawLine(cx - maxR, cy, cx + maxR, cy, horizCol);
    // Arrowhead on vertical crosshair: top when vertAxis > 0, bottom when < 0
    if (vertAxis > 0) {
        _sprite->drawLine(cx, cy - maxR, cx - 4, cy - maxR + 5, vertCol);
        _sprite->drawLine(cx, cy - maxR, cx + 4, cy - maxR + 5, vertCol);
    } else {
        _sprite->drawLine(cx, cy + maxR, cx - 4, cy + maxR - 5, vertCol);
        _sprite->drawLine(cx, cy + maxR, cx + 4, cy + maxR - 5, vertCol);
    }
    // Arrowhead on horizontal crosshair: right when horizAxis < 0, left when > 0
    if (horizAxis < 0) {
        _sprite->drawLine(cx + maxR, cy, cx + maxR - 5, cy - 4, horizCol);
        _sprite->drawLine(cx + maxR, cy, cx + maxR - 5, cy + 4, horizCol);
    } else {
        _sprite->drawLine(cx - maxR, cy, cx - maxR + 5, cy - 4, horizCol);
        _sprite->drawLine(cx - maxR, cy, cx - maxR + 5, cy + 4, horizCol);
    }

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
    //
    // Bubble always uses the standard UX tilt angles (_dispUxPitch/_dispUxRoll), which are
    // independent of the configured pitch/roll axes, so physical level is always shown correctly.
    // For StickC the display is at setRotation(3); its pixel axes are inverted relative to
    // rotation 1 (used by Core2/CoreS3), so flipSign = -1 keeps the bubble on the high side.
    static const float kDeg2Rad  = 0.017453293f;
    static const float kSin3     = 0.052335956f; // sinf(3°)
    float bubbleScale = (float)maxR / kSin3;
    bool isStickC = (M5.getBoard() == m5::board_t::board_M5StickCPlus2
                  || M5.getBoard() == m5::board_t::board_M5StickCPlus);
    float hAngle = isStickC ? _dispUxRoll  : _dispUxPitch;
    float vAngle = isStickC ? _dispUxPitch : _dispUxRoll;
    float flipSign = isStickC ? -1.0f : 1.0f;
    int bx = cx - (int)(flipSign * sinf(hAngle * kDeg2Rad) * bubbleScale);
    int by = cy + (int)(flipSign * sinf(vAngle * kDeg2Rad) * bubbleScale);
    bx = constrain(bx, cx - maxR, cx + maxR);
    by = constrain(by, cy - maxR, cy + maxR);
    int dotR = maxR / 9;
    if (dotR < 4) dotR = 4;
    _sprite->fillCircle(bx, by, dotR, _c(TFT_WHITE, n));
    _sprite->drawCircle(bx, by, dotR, _c(TFT_YELLOW, n));

    // Numeric readout — right panel
    char abuf[8];
    int px  = cx + maxR + 20;
    int icx = px + 9;  // axis-icon centre x

    // Numeric label icons.
    // In XY layout: pitch gets ↕ (vertical tilt), roll gets ↔ (horizontal tilt).
    // In YX layout the axes are swapped, so the icons swap too.
    uint16_t pCol = _c(TFT_CYAN,   n);
    uint16_t rCol = _c(TFT_ORANGE, n);
    int lyP  = _H *  5 / 135;
    int lyR  = _H * 62 / 135;
    int icyP = lyP + 8;
    int icyR = lyR + 8;
    if (yx) {
        _drawHorizIcon(_sprite, icx, icyP, pCol);  // pitch → ↔ in YX layout
        _drawVertIcon (_sprite, icx, icyR, rCol);  // roll  → ↕ in YX layout
    } else {
        _drawVertIcon (_sprite, icx, icyP, pCol);  // pitch → ↕ in XY layout
        _drawHorizIcon(_sprite, icx, icyR, rCol);  // roll  → ↔ in XY layout
    }
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(pCol);
    _sprite->setCursor(px + 20, lyP);
    _sprite->print("Pitch");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H * 25 / 135);
    fmtAngle(abuf, sizeof(abuf), _dispPitch);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(rCol);
    _sprite->setCursor(px + 20, lyR);
    _sprite->print("Roll");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H * 82 / 135);
    fmtAngle(abuf, sizeof(abuf), _dispRoll);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::Font0);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(px, _H * 118 / 135);
    _sprite->print("degrees");
}

void Display::_drawTime(const DeviceState& state) {
    bool n  = state.nightMode;
    int  cx = _W / 2;

    if (state.utcAnchorSec == 0) {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString("NO TIME SET", cx, _H / 2);
        _sprite->setTextDatum(textdatum_t::top_left);
        return;
    }

    // Timezone label top-left
    if (state.timezoneLabel[0] != '\0') {
        bool hasNonAscii = false;
        for (const char* p = state.timezoneLabel; *p; p++)
            if ((uint8_t)*p >= 0x80) { hasNonAscii = true; break; }
        if (hasNonAscii)
            _sprite->setFont(&fonts::lgfxJapanGothic_24);
        else
            _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_CYAN, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString(state.timezoneLabel, cx, 16);
        _sprite->setTextDatum(textdatum_t::top_left);
    }

    char timeBuf[12];
    if (state.siderealMode) {
        uint32_t lst = currentLstSeconds(state);
        snprintf(timeBuf, sizeof(timeBuf), "%02u:%02u:%02u",
                 lst / 3600, (lst % 3600) / 60, lst % 60);
    } else {
        // Local time = UTC + offset
        time_t localT = deviceCurrentTime(state) + (time_t)state.timezoneOffsetSec;
        struct tm ti;
        gmtime_r(&localT, &ti);
        snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d:%02d",
                 ti.tm_hour, ti.tm_min, ti.tm_sec);

        char dateBuf[12];
        snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday);
        _sprite->setFont(&fonts::Font7);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString(timeBuf, cx, _H * 66 / 135);
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
        _sprite->drawString(dateBuf, cx, _H * 114 / 135);
        _sprite->setTextDatum(textdatum_t::top_left);
        return;
    }

    // Sidereal: time only, no date
    _sprite->setFont(&fonts::Font7);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setTextDatum(textdatum_t::middle_center);
    _sprite->drawString(timeBuf, cx, _H * 66 / 135);
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawRADec(const DeviceState& state) {
    bool n = state.nightMode;
    int mx = _W / 24;   // ≈10px left margin at W=240
    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setCursor(mx, _H * 2 / 135);
    _sprite->print("RA");

    _sprite->setFont(&fonts::DejaVu40);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 28 / 135);
    _sprite->print(state.raText);

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setCursor(mx, _H * 68 / 135);
    _sprite->print("Dec");

    _sprite->setFont(&fonts::DejaVu40);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 94 / 135);
    _sprite->print(state.decText);
}

void Display::_drawAltAz(const DeviceState& state) {
    bool n = state.nightMode;
    int mx = _W / 24;
    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setCursor(mx, _H * 2 / 135);
    _sprite->print("Alt");

    _sprite->setFont(&fonts::DejaVu40);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 28 / 135);
    _sprite->print(state.altText);

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setCursor(mx, _H * 68 / 135);
    _sprite->print("Az");

    _sprite->setFont(&fonts::DejaVu40);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(mx, _H * 94 / 135);
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
    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setTextDatum(textdatum_t::top_center);
    _sprite->drawString("BATTERY", _W / 2, _H * 20 / 135);
    _sprite->setTextDatum(textdatum_t::top_left);

    // Bar geometry
    const int BAR_X = _W * 18 / 240;
    const int BAR_Y = _H * 53 / 135;
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
    int readY = _H * 106 / 135;
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
