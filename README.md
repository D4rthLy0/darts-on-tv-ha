# 🎯 Darts on TV for Home Assistant

Never miss the darts again. This adds a **UK darts TV schedule** to Home Assistant:

- **A sensor** (`sensor.darts_on_tv`) with every televised session for the next month: date, start time, tournament, round, venue and **TV channel(s)**, plus **who's playing** once the line-up is out.
- **A morning reminder** at 10:00 on darts days, sent to your phone, e.g.

  > 🎯 Darts on TV today – Grand Slam of Darts
  > 7:00pm – Group Stage Matches on Sky Sports Main Event (also Sky Sports+)
  > Luke Humphries v Joe Cullen
  > Michael van Gerwen v Jeffrey de Graaf
  > …

- **A dashboard card**: a "Next up" panel with tonight's line-up (and a LIVE tag while it's on), then a day-by-day list with date tiles and coloured channel badges (Sky blue, ITV teal).

UK only: the times and channels are UK TV listings, in UK time.

## Where the data comes from

No API key or account needed. Every 3 hours, `darts_tv.py` reads:

| What | Source |
|------|--------|
| Dates, times, rounds, channels | [wheresthematch.com – Live Darts on TV](https://www.wheresthematch.com/live-darts-on-tv/) |
| Who's playing (best effort) | the tournament page on [dartsnews.com](https://dartsnews.com/pdc) ("<Tournament> 2026: Results, Schedule, …") |

Both are public web pages, not official APIs, so:

- **If either site changes its layout, the script may stop finding data** until it's updated. When that happens the sensor shows no sessions or an `error` attribute; it never shows made-up data.
- Line-ups only appear once they are published (often the day before), only for the next 3 days, and only when real names are known (not "Winner Group A").
- Channels far ahead (e.g. the World Championship) may say **Channel TBC** until the listings site fills them in.
- Please keep the refresh interval at 3 hours or more to be kind to both sites.

## Install

1. Copy **`darts_tv.py`** into your Home Assistant config folder (`/config`). It only uses the Python standard library.
2. Copy **`packages/darts_on_tv.yaml`** into `/config/packages/`. If you don't use packages yet, add this to `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
   (Already have `command_line:`, `recorder:` or `automation:` in `configuration.yaml`? Packages merge with them, which is fine.)
3. In that file, change **`notify.YOUR_PHONE`** to your own notify entity (e.g. `notify.mobile_app_your_phone`).
4. Check the config (Developer tools → YAML → Check configuration) and restart Home Assistant.
5. For the card, install **button-card** (RomRider) from the Marketplace/HACS, then add a **Manual** card and paste in **`dashboard/darts_card.yaml`**.

Test the script on its own with `python3 /config/darts_tv.py`. It prints the JSON the sensor uses.

## Sensor

- **State**: start time of the next session (a timestamp).
- **`sessions`**: a list, each with `start` (ISO, UK time), `event`, `round`, `venue`, `channels` (list), `matches` (list of `"A v B"`, may be empty).
- **`updated`**: when the script last ran. **`error`**: only set if the listings couldn't be fetched.

## Notes

- Built for personal use with the help of Claude (Anthropic's AI). Use at your own risk, and please open an issue if a site change breaks it.
- Not affiliated with the PDC, Sky, ITV, WherestheMatch or Dartsnews. All listings belong to their owners.

## Licence

MIT
