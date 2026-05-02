#include "Display.h"
#include <math.h>
#include <time.h>

// --- CLite_GFX: exact hardware config from demo ---

CLite_GFX::CLite_GFX() {
    {
        auto cfg = _bus_instance.config();
        cfg.pin_mosi  = 15;
        cfg.pin_miso  = -1;
        cfg.pin_sclk  = 13;
        cfg.pin_dc    = 14;
        cfg.freq_write = 40000000;
        _bus_instance.config(cfg);
        _panel_instance.setBus(&_bus_instance);
    }
    {
        auto cfg = _panel_instance.config();
        cfg.invert       = true;
        cfg.pin_cs       = 5;
        cfg.pin_rst      = 12;
        cfg.pin_busy     = -1;
        cfg.panel_width  = 135;
        cfg.panel_height = 240;
        cfg.offset_x     = 52;
        cfg.offset_y     = 40;
        _panel_instance.config(cfg);
    }
    {
        auto cfg = _light_instance.config();
        cfg.pin_bl      = 27;
        cfg.invert      = false;
        cfg.freq        = 200;
        cfg.pwm_channel = 7;
        _light_instance.config(cfg);
        _panel_instance.setLight(&_light_instance);
    }
    setPanel(&_panel_instance);
}

// --- Display ---

void Display::begin() {
    _lcd.begin();
    _lcd.setRotation(3);   // landscape: 240 wide × 135 tall
    _lcd.setBrightness(128);
    _sprite = new LGFX_Sprite(&_lcd);
    _sprite->createSprite(_lcd.width(), _lcd.height());
}

void Display::setBrightness(uint8_t val) {
    _lcd.setBrightness(val);
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
        case SCREEN_MESSAGE:    _drawMessage(state);    break;
        default: break;
    }

    _drawBleIndicator(state.bleConnected);
    _flush();
}

// --- Screen renderers ---

static constexpr int CX = 80;   // bubble level center X
static constexpr int CY = 67;   // bubble level center Y
static constexpr int MAX_R = 55; // pixel radius for 3°

void Display::_drawClinometer(const DeviceState& state) {
    // Crosshairs
    _sprite->drawLine(CX, CY - MAX_R, CX, CY + MAX_R, TFT_DARKGREY);
    _sprite->drawLine(CX - MAX_R, CY, CX + MAX_R, CY, TFT_DARKGREY);

    // Concentric circles for 1°, 2°, 3°
    for (int deg = 1; deg <= 3; deg++) {
        int r = deg * MAX_R / 3;
        uint16_t col = (deg == 1) ? TFT_GREEN : (deg == 2) ? TFT_YELLOW : TFT_RED;
        _sprite->drawCircle(CX, CY, r, col);
    }

    // Bubble position (clamped to max radius)
    int bx = CX + (int)(state.tiltYDeg * MAX_R / 3.0f);
    int by = CY - (int)(state.tiltXDeg * MAX_R / 3.0f);
    bx = constrain(bx, CX - MAX_R, CX + MAX_R);
    by = constrain(by, CY - MAX_R, CY + MAX_R);
    _sprite->fillCircle(bx, by, 6, TFT_WHITE);
    _sprite->drawCircle(bx, by, 6, TFT_YELLOW);

    // Numeric readout — right panel
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_WHITE);
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
    _sprite->setTextColor(TFT_DARKGREY);
    _sprite->setCursor(155, 118);
    _sprite->print("degrees");
}

void Display::_drawTime(const DeviceState& state) {
    time_t t = deviceCurrentTime(state);
    if (t == 0) {
        _sprite->setFont(&fonts::Font4);
        _sprite->setTextColor(TFT_DARKGREY);
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
    _sprite->setTextColor(TFT_WHITE);
    _sprite->setTextDatum(textdatum_t::middle_center);
    _sprite->drawString(timeBuf, 120, 50);

    // Date: YYYY-MM-DD smaller below
    char dateBuf[12];
    snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d",
             ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday);
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_LIGHTGREY);
    _sprite->drawString(dateBuf, 120, 105);
    _sprite->setTextDatum(textdatum_t::top_left);
}

void Display::_drawRADec(const DeviceState& state) {
    _sprite->setTextColor(TFT_DARKGREY);
    _sprite->setFont(&fonts::Font2);
    _sprite->setCursor(10, 10);
    _sprite->print("RA");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(TFT_WHITE);
    _sprite->setCursor(10, 28);
    _sprite->print(state.raText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_DARKGREY);
    _sprite->setCursor(10, 72);
    _sprite->print("Dec");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(TFT_WHITE);
    _sprite->setCursor(10, 90);
    _sprite->print(state.decText);
}

void Display::_drawAltAz(const DeviceState& state) {
    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_DARKGREY);
    _sprite->setCursor(10, 10);
    _sprite->print("Alt");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(TFT_WHITE);
    _sprite->setCursor(10, 28);
    _sprite->print(state.altText);

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_DARKGREY);
    _sprite->setCursor(10, 72);
    _sprite->print("Az");

    _sprite->setFont(&fonts::Font4);
    _sprite->setTextColor(TFT_WHITE);
    _sprite->setCursor(10, 90);
    _sprite->print(state.azText);
}

void Display::_drawMessage(const DeviceState& state) {
    if (!state.messageActive) return;

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
        _sprite->setTextColor(TFT_YELLOW);
        _sprite->setTextDatum(textdatum_t::top_right);
        _sprite->drawString(countdown, 210, 4);
        _sprite->setTextDatum(textdatum_t::top_left);
    }

    // Message text — simple line wrapping at ~28 chars
    const int LINE_LEN = 28;
    const int LINE_H   = 18;
    int startY = 20;

    _sprite->setFont(&fonts::Font2);
    _sprite->setTextColor(TFT_WHITE);

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
        _sprite->setTextColor(TFT_DARKGREY);
        _sprite->setTextDatum(textdatum_t::bottom_center);
        _sprite->drawString(hint, 120, 133);
        _sprite->setTextDatum(textdatum_t::top_left);
    }
}

void Display::_drawBleIndicator(bool connected) {
    uint16_t col = connected ? TFT_GREEN : 0x4208; // dark gray when not connected
    _sprite->fillCircle(228, 8, 5, col);
}

void Display::_flush() {
    _sprite->pushSprite(0, 0);
}
