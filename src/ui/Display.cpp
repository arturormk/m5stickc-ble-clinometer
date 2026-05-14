#include "Display.h"
#include <math.h>
#include <time.h>

void Display::begin() {
    M5.Display.setRotation(3);
    M5.Display.setBrightness(128);
    _W = M5.Display.width();
    _H = M5.Display.height();
    _sprite = new LGFX_Sprite(&M5.Display);
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

    // Bubble position (clamped to max radius)
    int bx = cx + (int)(state.tiltYDeg * maxR / 3.0f);
    int by = cy - (int)(state.tiltXDeg * maxR / 3.0f);
    bx = constrain(bx, cx - maxR, cx + maxR);
    by = constrain(by, cy - maxR, cy + maxR);
    int dotR = maxR / 9;
    if (dotR < 4) dotR = 4;
    _sprite->fillCircle(bx, by, dotR, _c(TFT_WHITE, n));
    _sprite->drawCircle(bx, by, dotR, _c(TFT_YELLOW, n));

    // Numeric readout — right panel
    int px = cx + maxR + 20;
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(px, _H *  8 / 135);
    _sprite->print("X:");
    _sprite->setFont(&fonts::Font4);
    _sprite->setCursor(px, _H * 22 / 135);
    _sprite->printf("%+.2f", state.tiltXDeg);

    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(px, _H * 68 / 135);
    _sprite->print("Y:");
    _sprite->setFont(&fonts::Font4);
    _sprite->setCursor(px, _H * 82 / 135);
    _sprite->printf("%+.2f", state.tiltYDeg);

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

    // Time: HH:MM:SS large centered
    char timeBuf[12];
    snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d:%02d",
             ti.tm_hour, ti.tm_min, ti.tm_sec);
    _sprite->setFont(&fonts::Font7);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setTextDatum(textdatum_t::middle_center);
    _sprite->drawString(timeBuf, cx, _H * 50 / 135);

    _sprite->setFont(&fonts::Font2);
    if (state.siderealMode) {
        _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
        const char* lbl = state.timezoneLabel[0] ? state.timezoneLabel : "LST";
        _sprite->drawString(lbl, cx, _H * 105 / 135);
    } else {
        char dateBuf[12];
        snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday);
        _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
        _sprite->drawString(dateBuf, cx, _H * 105 / 135);
        if (state.timezoneLabel[0] != '\0') {
            _sprite->setTextColor(_c(TFT_DARKGREY, n));
            _sprite->drawString(state.timezoneLabel, cx, _H * 118 / 135);
        }
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

    // Font2 char width ≈ 8px; leave ~2-char margin each side
    const int LINE_LEN = (_W / 8) - 2;
    const int LINE_H   = _H * 18 / 135;
    const int startY   = _H * 20 / 135;

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_WHITE, n));

    const char* p = state.messageText;
    int len = strlen(p);
    int y = startY;
    const int bottomLimit = _H - LINE_H;

    while (*p && y < bottomLimit) {
        char line[64];
        int take = 0;

        if (len <= LINE_LEN) {
            take = len;
        } else {
            take = LINE_LEN;
            int back = take;
            while (back > 0 && p[back] != ' ') back--;
            if (back > 0) take = back;
        }

        int safeTake = take < 63 ? take : 63;
        strncpy(line, p, safeTake);
        line[safeTake] = '\0';

        _sprite->setTextDatum(textdatum_t::top_center);
        _sprite->drawString(line, _W / 2, y);

        p += take;
        len -= take;
        if (*p == ' ') { p++; len--; }
        y += LINE_H;
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
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
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
