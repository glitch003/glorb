# Chargers

## Drive pack (72 V Tesla 3s2p) — Elcon UHF 6.6 kW w/ CANbus × 2

Model **HK-LF-108-60** (Elcon/TC Charger "UHF" 4th gen), two units on the cart.

| Spec | Value |
| --- | --- |
| AC input | 90–265 VAC, 45–65 Hz (works on 120 V or 240 V) |
| Max AC input current | **32 A** per charger at full 6.6 kW output |
| Output | 45–177 VDC range (rated 65–140 V), 60 A max, 6.6 kW |
| Efficiency | ~93–95 % |
| Control | CANbus (250/500 kbps), needs BMS/EVCC to command voltage & current |
| Enclosure | IP67, –40 to +65 °C |

**240 V draw:** at full 6.6 kW, ≈ 6600 W ÷ 240 V ÷ 0.94 eff ≈ **29–32 A each → ~60–64 A for both** (needs a 40 A circuit each, or a 70–80 A feed for the pair). On 120 V the charger derates to roughly 2–3 kW (limited by the ~16–20 A input it will pull from a 120 V outlet), so 240 V is the only way to get full rate.

Links: [EV Source](https://evsource.com/products/charger-elcon-uhf-6-6kw-w-canbus), [EV West](https://evwest.com/elcon-6-6kw-hk-lf-108-60-can-bus-charger-with-evcc), [Elcon 4th gen page](https://elconchargers.com/?page_id=93)

## 12 V chargers (aux / EG4 pack)

All units 12 V output. Efficiency = wall watts / output amp (lower is better).

| Output A | Wall W | Eff (W/A) | Cost ea | Charge time | 240 V | Adj | Notes | Link |
| ---: | ---: | ---: | ---: | --- | :---: | :---: | --- | --- |
| 30 | 500 | 16.67 | $200 | 13.3 h | n | y | — | [Victron 12/30](https://www.amazon.com/Victron-Energy-12-Volt-Battery-Bluetooth/dp/B08NY23BKF/ref=pd_lpo_2?pd_rd_i=B08NY23BKF&th=1) |
| 80 | 1500 | 18.75 | $850 | 5 h | y | n | — | [Lithiumion CXC1280](https://www.lithiumion-batteries.com/products/product/cxc1280) |
| 50 | 1200 | 24 | $700 | 8 h | y | n | — | [Lithiumion 12V 50A](https://www.lithiumion-batteries.com/products/product/12v-50a-lithium-ion-battery-charger) |
| 70 | 1200 | 17.14 | $800 | 5.7 h | y | y | — | [Inverter Supply 70 A](https://www.invertersupply.com/index.php?main_page=product_info&products_id=199416) |
| 50 | ? | ? | $455 | 8 h | — | — | — | [LBP 12V 50A waterproof](https://www.lithiumbatterypower.com/products/lithium-12v-50a-waterproof-electronic-charger) |
| 60 | 1000 | 16.67 | $268 | 6.67 h | n | n | — | [Battle Born / Progressive Dynamics 60 A](https://battlebornbatteries.com/product/progressive-dynamics-12v-60-amp-lifepo4-battery-charger/) |
| 75 | 1200 | 16 | $264 | 5.33 h | n | y | — | [AIMS 75 A](https://www.amazon.com/AIMS-Power-CON120AC1224DC-Converter-Battery/dp/B07N1K43NQ/ref=psdc_15719911_t1_B07DP3X16F) |
| 60 | ? | ? | $152 | 6.67 h | y | y | No reviews, worried it sucks | [Amazon adjustable 60 A](https://www.amazon.com/Maintainer-Adjustable-Lithium-Iron-Rechargeable-Desulfator/dp/B09Z25WQPY) |
| 50 | 900 | 18 | $543.575 | 8 h | y | — | 3-bank charger, modeled as 2 banks (numbers ÷2) | Victron Centaur |
| 60 | 1380 | 23 | $436 | 6.67 h | y | n | — | [Mean Well PB-1000-12](https://www.meanwell-web.com/en-gb/ac-dc-single-output-intelligent-battery-charger-pb--1000--12) |

## Other chargers on hand (from parts list)

- **12 V 80 A** — <https://www.lithiumion-batteries.com/products/product/cxc1280>
- **12 V 40 A** — <https://www.amazon.com/Ampere-Time-Multi-Stage-Efficiency-Batteries/dp/B09SKLM5M9>
- **24 V 25 A** — <https://www.lithiumion-batteries.com/products/lithium-ion-chargers/24v-lithium-ion-battery-chargers/24v-45a-lithium-battery-charger>
- **12 V 30 A Victron** — <https://www.amazon.com/Victron-Energy-12-Volt-Battery-Bluetooth/dp/B08NY23BKF/ref=pd_lpo_2?pd_rd_i=B08NY23BKF&th=1>
- **Various incl. 72 V** — <https://www.lnleeparts.com/plus/view.php?aid=67>
