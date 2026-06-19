/// @file    nano_sm16703_powertest.ino
/// @brief   Power-draw bench test for a 5 m 24V SM16703 LED tube.
/// @board   Arduino Nano (ATmega328P, 16 MHz)
///
/// Serial-controlled so you can flip states while watching the inline
/// DC power meter — no reflashing between readings.
///
/// Open Serial Monitor @ 115200 and send a single char:
///   i  → idle      (all pixels commanded OFF / black, strip still powered)
///   w  → full white at brightness 255  (the spec-confirming max draw)
///   3  → white at 30% brightness        (validates linear dimming claim)
///   r  → red only  (single-channel draw, ~1/3 of white)
///
/// Record meter A / W for each. Divide by 5 for per-meter figures,
/// then scale to the planned tube count.

#include <FastLED.h>

#define DATA_PIN    7
#define NUM_LEDS    80      // 5 m strip — 16 pixels/m (6 LEDs per IC group)
#define COLOR_ORDER RGB
#define LED_TYPE    SM16703

CRGB leds[NUM_LEDS];

void fill(CRGB c, uint8_t bright) {
  FastLED.setBrightness(bright);
  fill_solid(leds, NUM_LEDS, c);
  FastLED.show();
}

void setup() {
  Serial.begin(115200);
  FastLED.addLeds<LED_TYPE, DATA_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  fill(CRGB::Black, 0);   // start idle
  Serial.println(F("Ready. Send: i=idle  w=white100%  3=white30%  r=red"));
}

void loop() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'i': fill(CRGB::Black, 0);   Serial.println(F("IDLE (all off)"));      break;
    case 'w': fill(CRGB::White, 255); Serial.println(F("WHITE 100%"));          break;
    case '3': fill(CRGB::White, 77);  Serial.println(F("WHITE 30% (bri 77)"));  break;
    case 'r': fill(CRGB::Red, 255);   Serial.println(F("RED 100%"));            break;
    default: break;
  }
}
