#include "Display.h"
#include "../version.h"
#include <lgfx/Fonts/GFXFF/FreeSans9pt7b.h>
#include <math.h>
#include <time.h>

void Display::begin() {
    bool isStickC = (M5.getBoard() == m5::board_t::board_M5StickCPlus2
                  || M5.getBoard() == m5::board_t::board_M5StickCPlus);
    M5.Display.setRotation(isStickC ? 3 : 1);
    M5.Display.setBrightness(BRIGHTNESS_FULL);
    _lastTiltActivityMs = millis();
    _W = M5.Display.width();
    _H = M5.Display.height();
    _sprite = new LGFX_Sprite(&M5.Display);
    _sprite->setColorDepth(8);
    _sprite->createSprite(_W, _H);
}

void Display::setBrightness(uint8_t val) {
    M5.Display.setBrightness(val);
}

void Display::_updateBrightness(const DeviceState& state) {
    uint32_t now = millis();

    // Track tilt activity: reset clock whenever angle moves beyond threshold
    if (fabsf(state.pitchDeg - _dimPitchRef) > DIM_STABLE_DEG ||
        fabsf(state.rollDeg  - _dimRollRef)  > DIM_STABLE_DEG) {
        _dimPitchRef        = state.pitchDeg;
        _dimRollRef         = state.rollDeg;
        _lastTiltActivityMs = now;
    }

    uint8_t target;
    if (state.nightMode) {
        target = BRIGHTNESS_NIGHT;
    } else if (state.streamEnabled
               || (now - state.lastBleCommandMs) < DIM_TIMEOUT_MS
               || (now - _lastTiltActivityMs)    < DIM_TIMEOUT_MS) {
        target = BRIGHTNESS_FULL;
    } else {
        target = BRIGHTNESS_DIM;
    }

    if (target != _currentBrightness) {
        setBrightness(target);
        _currentBrightness = target;
    }
}

void Display::update(const DeviceState& state) {
    _updateBrightness(state);
    uint32_t now = millis();
    uint32_t interval = (state.screenIndex == SCREEN_CLINOMETER ||
                         state.screenIndex == SCREEN_MESSAGE) ? 100 : 200;
    if ((now - _lastRefreshMs) < interval) return;
    _lastRefreshMs = now;

    if (state.screenIndex == SCREEN_CLINOMETER && _hasLastClinoState) {
        bool pitchSame = fabsf(state.pitchDeg - _lastClinoState.pitchDeg) < 0.1f;
        bool rollSame  = fabsf(state.rollDeg  - _lastClinoState.rollDeg)  < 0.1f;
        if (pitchSame && rollSame
                && state.batteryLevel == _lastClinoState.batteryLevel
                && state.bleConnected == _lastClinoState.bleConnected
                && state.nightMode    == _lastClinoState.nightMode
                && state.imuAvailable == _lastClinoState.imuAvailable
                && state.upsideDown   == _lastClinoState.upsideDown
                && state.pitchAxis    == _lastClinoState.pitchAxis
                && state.rollAxis     == _lastClinoState.rollAxis) {
            return;
        }
    }
    if (state.screenIndex == SCREEN_CLINOMETER) {
        _lastClinoState    = state;
        _hasLastClinoState = true;
    }

    _sprite->fillScreen(TFT_BLACK);

    switch (state.screenIndex) {
        case SCREEN_CLINOMETER: _drawClinometer(state); break;
        case SCREEN_TIME:       _drawTime(state);       break;
        case SCREEN_RADEC:      _drawRADec(state);      break;
        case SCREEN_ALTAZ:      _drawAltAz(state);      break;
        case SCREEN_BATTERY:    _drawBattery(state);    break;
        case SCREEN_MESSAGE:    _drawMessage(state);    break;
        case SCREEN_SYSINFO_1:
        case SCREEN_SYSINFO_2:
        case SCREEN_SYSINFO_3:
            _drawSysInfo(state, state.screenIndex - SCREEN_SYSINFO_1 + 1); break;
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
    // Convention: uxRoll > 0 = right side up; uxPitch > 0 = top up. Bubble moves toward the
    // high side, so bx increases with uxRoll and by decreases with uxPitch.
    // When upside down (guz < 0) the screen appears 180°-rotated to the viewer, so both
    // offsets are negated to keep the bubble tracking the physically high side.
    static const float kDeg2Rad  = 0.017453293f;
    static const float kSin3     = 0.052335956f; // sinf(3°)
    float bubbleScale = (float)maxR / kSin3;
    float flipSign = state.upsideDown ? -1.0f : 1.0f;
    int bx = cx + (int)(flipSign * sinf(_dispUxRoll  * kDeg2Rad) * bubbleScale);
    int by = cy - (int)(flipSign * sinf(_dispUxPitch * kDeg2Rad) * bubbleScale);
    bx = constrain(bx, cx - maxR, cx + maxR);
    by = constrain(by, cy - maxR, cy + maxR);
    int dotR = maxR / 9;
    if (dotR < 4) dotR = 4;
    _sprite->fillCircle(bx, by, dotR, _c(TFT_WHITE, n));
    _sprite->drawCircle(bx, by, dotR, _c(TFT_YELLOW, n));

    // Numeric readout — right panel
    char abuf[8];
    int px  = cx + maxR + 20;
    int icx = px + 5;  // axis-icon centre x

    // Numeric label icons.
    // In XY layout: pitch gets ↕ (vertical tilt), roll gets ↔ (horizontal tilt).
    // In YX layout the axes are swapped, so the icons swap too.
    uint16_t pCol = _c(TFT_CYAN,   n);
    uint16_t rCol = _c(TFT_ORANGE, n);
    int lyP  = _H * 14 / 135;
    int lyR  = _H * 68 / 135;
    int icyP = lyP + 8;
    int icyR = lyR + 8;
    if (yx) {
        _drawHorizIcon(_sprite, icx, icyP, pCol);  // pitch → ↔ in YX layout
        _drawVertIcon (_sprite, icx, icyR, rCol);  // roll  → ↕ in YX layout
    } else {
        _drawVertIcon (_sprite, icx, icyP, pCol);  // pitch → ↕ in XY layout
        _drawHorizIcon(_sprite, icx, icyR, rCol);  // roll  → ↔ in XY layout
    }
    _sprite->setFont(&fonts::FreeSans9pt7b);
    _sprite->setTextColor(pCol);
    _sprite->setCursor(px + 16, lyP);
    _sprite->print("Pitch");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H * 36 / 135);
    fmtAngle(abuf, sizeof(abuf), _dispPitch);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::FreeSans9pt7b);
    _sprite->setTextColor(rCol);
    _sprite->setCursor(px + 16, lyR);
    _sprite->print("Roll");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H * 92 / 135);
    fmtAngle(abuf, sizeof(abuf), _dispRoll);
    _sprite->print(abuf);

    _sprite->setFont(&fonts::Font0);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(px, _H * 118 / 135);
    _sprite->print("degrees");

    // Battery bar — 10 segments at bottom of right panel; lit up to level, dim beyond
    if (state.batteryLevel >= 0) {
        int lvl = state.batteryLevel;
        uint16_t col = (lvl < 20) ? _c(0x6000u, n)   // dark red
                     : (lvl < 40) ? _c(0x7A40u, n)   // dark amber
                     :              _c(0x0340u,  n);  // dark green
        uint16_t dim = _c(0x2104u, n);
        for (int i = 0; i <= 9; i++)
            _sprite->fillRect(px + i * 7, _H - 6, 6, 4, lvl >= i * 10 ? col : dim);
    }
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
    int readY = _H * 104 / 135;
    int voltX = BAR_X + BAR_W * 3 / 8;
    int pctX  = BAR_X + BAR_W * 6 / 8;

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

    // Hint that BtnB cycles through system info pages
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setTextDatum(textdatum_t::bottom_center);
    _sprite->drawString("B: system info", _W / 2, _H - 2);

    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawSysInfo(const DeviceState& state, int page) {
    bool n = state.nightMode;

    // Title
    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_CYAN, n));
    _sprite->setTextDatum(textdatum_t::top_center);
    _sprite->drawString("SYSTEM INFO", _W / 2, _H * 4 / 135);
    _sprite->setTextDatum(textdatum_t::top_left);

    const int lx   = _W * 10 / 240;
    const int vx   = _W * 90 / 240;
    const int row0 = _H * 28 / 135;
    const int rowH = _H * 19 / 135;

    _sprite->setFont(&fonts::Font2);

    // --- Page 1: runtime ---
    if (page == 1) {
        // FW version
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("FW", lx, row0);
        _sprite->setTextColor(_c(TFT_CYAN, n));
        _sprite->drawString(FW_VERSION, vx, row0);

        // Uptime
        uint32_t sec = millis() / 1000;
        uint32_t h   = sec / 3600; sec %= 3600;
        uint32_t m   = sec / 60;   sec %= 60;
        char upBuf[20];
        snprintf(upBuf, sizeof(upBuf), "%luh %02lum %02lus",
                 (unsigned long)h, (unsigned long)m, (unsigned long)sec);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Up", lx, row0 + rowH);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(upBuf, vx, row0 + rowH);

        // Free heap (quick view)
        char heapBuf[24];
        snprintf(heapBuf, sizeof(heapBuf), "%lu kB free",
                 (unsigned long)ESP.getFreeHeap() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Heap", lx, row0 + rowH * 2);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(heapBuf, vx, row0 + rowH * 2);

        // IMU die temperature
        float imuTemp = 0.0f;
        bool  hasTemp = M5.Imu.getTemp(&imuTemp);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Temp", lx, row0 + rowH * 3);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        if (hasTemp) {
            char tempBuf[16];
            snprintf(tempBuf, sizeof(tempBuf), "%.1f C", imuTemp);
            _sprite->drawString(tempBuf, vx, row0 + rowH * 3);
        } else {
            _sprite->drawString("N/A", vx, row0 + rowH * 3);
        }

        // Battery charging state; append current only if PMIC provides it
        auto    chgState = M5.Power.isCharging();
        int32_t batMa    = M5.Power.getBatteryCurrent();
        char    batBuf[24];
        bool    chgKnown = (chgState != m5::Power_Class::charge_unknown);
        if (!chgKnown && batMa == 0) {
            snprintf(batBuf, sizeof(batBuf), "--");  // no PMIC on this board
        } else {
            const char* chgLabel =
                (chgState == m5::Power_Class::is_charging)    ? "CHG" :
                (chgState == m5::Power_Class::is_discharging) ? "DSG" : "?";
            if (batMa != 0) {
                snprintf(batBuf, sizeof(batBuf), "%s %+ld mA", chgLabel, (long)batMa);
            } else {
                snprintf(batBuf, sizeof(batBuf), "%s", chgLabel);
            }
        }
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Batt", lx, row0 + rowH * 4);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(batBuf, vx, row0 + rowH * 4);

    // --- Page 2: memory detail ---
    } else if (page == 2) {
        char buf[32];

        snprintf(buf, sizeof(buf), "%lu kB", (unsigned long)ESP.getHeapSize() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Total", lx, row0);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0);

        snprintf(buf, sizeof(buf), "%lu kB", (unsigned long)ESP.getFreeHeap() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Free", lx, row0 + rowH);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH);

        snprintf(buf, sizeof(buf), "%lu kB", (unsigned long)ESP.getMinFreeHeap() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("MinFree", lx, row0 + rowH * 2);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH * 2);

        snprintf(buf, sizeof(buf), "%lu kB", (unsigned long)ESP.getMaxAllocHeap() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("MaxBlk", lx, row0 + rowH * 3);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH * 3);

        uint32_t psram = ESP.getFreePsram();
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("PSRAM", lx, row0 + rowH * 4);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        if (psram > 0) {
            snprintf(buf, sizeof(buf), "%lu kB", (unsigned long)psram / 1024);
            _sprite->drawString(buf, vx, row0 + rowH * 4);
        } else {
            _sprite->drawString("none", vx, row0 + rowH * 4);
        }

    // --- Page 3: chip & flash ---
    } else {
        char buf[32];

        // Chip model + revision
        snprintf(buf, sizeof(buf), "%s r%u", ESP.getChipModel(), ESP.getChipRevision());
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Chip", lx, row0);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0);

        // Cores + CPU freq
        snprintf(buf, sizeof(buf), "%u core  %lu MHz",
                 ESP.getChipCores(), (unsigned long)ESP.getCpuFreqMHz());
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("CPU", lx, row0 + rowH);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH);

        // Flash size
        snprintf(buf, sizeof(buf), "%lu MB", (unsigned long)ESP.getFlashChipSize() / 1024 / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Flash", lx, row0 + rowH * 2);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH * 2);

        // Sketch used / free
        snprintf(buf, sizeof(buf), "%lu / %lu kB",
                 (unsigned long)ESP.getSketchSize()      / 1024,
                 (unsigned long)ESP.getFreeSketchSpace() / 1024);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("Sketch", lx, row0 + rowH * 3);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(buf, vx, row0 + rowH * 3);

        // SDK version
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->drawString("IDF", lx, row0 + rowH * 4);
        _sprite->setTextColor(_c(TFT_WHITE, n));
        _sprite->drawString(ESP.getSdkVersion(), vx, row0 + rowH * 4);
    }

    // Page indicator  "1/3"
    char pageBuf[4];
    snprintf(pageBuf, sizeof(pageBuf), "%d/3", page);
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setTextDatum(textdatum_t::bottom_right);
    _sprite->drawString(pageBuf, _W - _W * 14 / 240, _H - 2);
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
