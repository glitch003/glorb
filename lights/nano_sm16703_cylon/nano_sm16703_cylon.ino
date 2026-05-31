/// @file    nano_sm16703_cylon.ino
/// @brief   Larson scanner (Cylon) on a 5 m 24V SM16703 LED tube
/// @board   Arduino Nano (ATmega328P, 16 MHz)
///
/// Strip: 24V SM16703, SMD3535, 96 LEDs/m per side (192 total, double-sided).
/// 6 physical LEDs per SM16703 IC → 16 addressable pixels/m → 80 pixels for 5 m.
/// Color order confirmed RGB on this strip.

#include <FastLED.h>

#define DATA_PIN    7
#define NUM_LEDS    80      // 5 m strip — 16 pixels/m (6 LEDs per IC group)
#define BRIGHTNESS  255
#define COLOR_ORDER RGB
#define LED_TYPE    SM16703

CRGB leds[NUM_LEDS];

void setup() {
  FastLED.addLeds<LED_TYPE, DATA_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
}

void fadeall() {
  for (int i = 0; i < NUM_LEDS; i++) { leds[i].nscale8(250); }
}

void loop() {
  static uint8_t hue = 0;

  for (int i = 0; i < NUM_LEDS; i++) {
    leds[i] = CHSV(hue++, 255, 255);
    FastLED.show();
    fadeall();
    delay(10);
  }

  for (int i = NUM_LEDS - 1; i >= 0; i--) {
    leds[i] = CHSV(hue++, 255, 255);
    FastLED.show();
    fadeall();
    delay(10);
  }
}
