#include "Display.h"
#include <math.h>
#include <time.h>

void Display::begin() {
    M5.Display.setRotation(3);   // landscape: 240 wide × 135 tall
    M5.Display.setBrightness(128);
    _sprite = new LGFX_Sprite(&M5.Display);
    _sprite->createSprite(M5.Display.width(), M5.Display.height());
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

static constexpr int CX = 80;   // bubble level center X
static constexpr int CY = 67;   // bubble level center Y
static constexpr int MAX_R = 55; // pixel radius for 3°

void Display::_drawClinometer(const DeviceState& state) {
    bool n = state.nightMode;

    // Crosshairs
    _sprite->drawLine(CX, CY - MAX_R, CX, CY + MAX_R, _c(TFT_DARKGREY, n));
    _sprite->drawLine(CX - MAX_R, CY, CX + MAX_R, CY, _c(TFT_DARKGREY, n));

    // Concentric circles for 1°, 2°, 3°
    for (int deg = 1; deg <= 3; deg++) {
        int r = deg * MAX_R / 3;
        uint16_t col = (deg == 1) ? _c(TFT_GREEN, n) : (deg == 2) ? _c(TFT_YELLOW, n) : _c(TFT_RED, n);
        _sprite->drawCircle(CX, CY, r, col);
    }

    // Bubble position (clamped to max radius)
    int bx = CX + (int)(state.tiltYDeg * MAX_R / 3.0f);
    int by = CY - (int)(state.tiltXDeg * MAX_R / 3.0f);
    bx = constrain(bx, CX - MAX_R, CX + MAX_R);
    by = constrain(by, CY - MAX_R, CY + MAX_R);
    _sprite->fillCircle(bx, by, 6, _c(TFT_WHITE, n));
    _sprite->drawCircle(bx, by, 6, _c(TFT_YELLOW, n));

    // Numeric readout — right panel
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(155, 8);
    _sprite->print("X:");
    _sprite->setCursor(155, 22);
    _sprite->setFont(&fonts::Font4);
    _sprite->printf("%+.2f", state.tiltXDeg);

    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(155, 68);
    _sprite->print("Y:");
    _sprite->setCursor(155, 82);
    _sprite->setFont(&fonts::Font4);
    _sprite->printf("%+.2f", state.tiltYDeg);

    // Degree symbol area label
    _sprite->setFont(&fonts::Font0);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(155, 118);
    _sprite->print("degrees");
}

void Display::_drawTime(const DeviceState& state) {
    bool n = state.nightMode;
    time_t t = deviceCurrentTime(state);
    if (t == 0) {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(_c(TFT_DARKGREY, n));
        _sprite->setTextDatum(textdatum_t::middle_center);
        _sprite->drawString("NO TIME SET", 120, 67);
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
    _sprite->drawString(timeBuf, 120, 50);

    // Date: YYYY-MM-DD smaller below
    char dateBuf[12];
    snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d",
             ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday);
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_LIGHTGREY, n));
    _sprite->drawString(dateBuf, 120, 105);
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawRADec(const DeviceState& state) {
    bool n = state.nightMode;
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(10, 10);
    _sprite->print("RA");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(10, 28);
    _sprite->print(state.raText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(10, 72);
    _sprite->print("Dec");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(10, 90);
    _sprite->print(state.decText);
}

void Display::_drawAltAz(const DeviceState& state) {
    bool n = state.nightMode;
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(10, 10);
    _sprite->print("Alt");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(10, 28);
    _sprite->print(state.altText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_DARKGREY, n));
    _sprite->setCursor(10, 72);
    _sprite->print("Az");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setCursor(10, 90);
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
        _sprite->drawString(countdown, 210, 4);
        _sprite->setTextDatum(textdatum_t::top_left);
    }

    // Message text — simple line wrapping at ~28 chars
    const int LINE_LEN = 28;
    const int LINE_H   = 18;
    int startY = 20;

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(_c(TFT_WHITE, n));

    const char* p = state.messageText;
    int len = strlen(p);
    int y = startY;

    while (*p && y < 110) {
        char line[LINE_LEN + 1];
        int take = 0;

        // Try to break at word boundary
        if (len <= LINE_LEN) {
            take = len;
        } else {
            take = LINE_LEN;
            int back = take;
            while (back > 0 && p[back] != ' ') back--;
            if (back > 0) take = back;
        }

        strncpy(line, p, take);
        line[take] = '\0';

        _sprite->setTextDatum(textdatum_t::top_center);
        _sprite->drawString(line, 120, y);

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
        _sprite->drawString(hint, 120, 133);
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
    _sprite->drawString("BATTERY", 110, 8);
    _sprite->setTextDatum(textdatum_t::top_left);

    // Bar geometry
    const int BAR_X = 18, BAR_Y = 36, BAR_W = 192, BAR_H = 28;
    const int TIP_W = 7,  TIP_H = 14;

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

    // Voltage
    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(_c(TFT_WHITE, n));
    _sprite->setTextDatum(textdatum_t::middle_center);
    if (state.batteryVoltage > 0.5f) {
        char voltBuf[12];
        snprintf(voltBuf, sizeof(voltBuf), "%.2f V", state.batteryVoltage);
        _sprite->drawString(voltBuf, 90, 92);
    } else {
        _sprite->drawString("-- V", 90, 92);
    }

    // Percentage
    if (pct >= 0) {
        char pctBuf[8];
        snprintf(pctBuf, sizeof(pctBuf), "%d%%", pct);
        _sprite->drawString(pctBuf, 185, 92);
    } else {
        _sprite->drawString("--%", 185, 92);
    }
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawBleIndicator(bool connected, bool nightMode) {
    uint16_t col = connected ? _c(TFT_GREEN, nightMode) : _c(0x4208, nightMode);
    _sprite->fillCircle(228, 8, 5, col);
}

void Display::_flush() {
    _sprite->pushSprite(0, 0);
}

uint16_t Display::_c(uint16_t color, bool night) const {
    if (!night || color == TFT_BLACK) return color;
    if (color == TFT_GREEN) return 0xFB00u; // warm orange-red accent in RGB565
    return TFT_RED;
}
