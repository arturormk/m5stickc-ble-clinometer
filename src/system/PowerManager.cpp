#include "PowerManager.h"
#include <M5Unified.h>
#include <esp_system.h>

void PowerManager::begin() {
    auto cfg = M5.config();
    cfg.serial_baudrate = 115200;
    cfg.output_power    = true;
    cfg.internal_imu    = true;
    cfg.internal_rtc    = true;
    cfg.internal_spk    = true;
    M5.begin(cfg);

    if (M5.Speaker.isEnabled()) {
        struct { m5::board_t board; uint8_t volume; } kVol[] = {
            { m5::board_t::board_M5StickS3,     128 },
            { m5::board_t::board_M5StickCPlus2, 100 },
            { m5::board_t::board_M5StickCPlus,  100 },
            { m5::board_t::board_M5Stack,        40 },
            { m5::board_t::board_M5StackCore2,   40 },
            { m5::board_t::board_M5StackCoreS3,  40 },
        };
        uint8_t vol = 50;
        m5::board_t b = M5.getBoard();
        for (const auto& e : kVol) {
            if (b == e.board) { vol = e.volume; break; }
        }
        M5.Speaker.setVolume(vol);
        M5.Speaker.tone(3600, 40);
    }
}

float PowerManager::readBatteryVoltage() {
    if (M5.getBoard() == m5::board_t::board_M5Stack) {
        // board_M5Stack (Grey) does not report a reliable voltage via getBatteryVoltage();
        // estimate from battery level using a 4-step lookup.
        int lvl = M5.Power.getBatteryLevel();
        if      (lvl < 25) return 3.1f;
        else if (lvl < 50) return 3.4f;
        else if (lvl < 75) return 3.8f;
        else               return 4.0f;
    }
    float v = M5.Power.getBatteryVoltage() / 1000.0f;
    // Discard implausible readings; e.g. AXP2101 on StickC Plus 2 returns ~6.3 V
    // when an ENV III unit is connected via Grove (upstream M5Unified bug).
    if (v > 5.0f) return 0.0f;
    return v;
}

int PowerManager::readBatteryLevel() {
    return M5.Power.getBatteryLevel();
}

void PowerManager::reboot() {
    esp_restart();
}

void PowerManager::deepSleep() {
    M5.Power.powerOff();
}
