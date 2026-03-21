<div dir="rtl">

# צבע אדום - אינטגרציה ל-Home Assistant

[![HACS Validation](https://github.com/dn5qMDW3/tzevaadom/actions/workflows/hacs-validate.yml/badge.svg)](https://github.com/dn5qMDW3/tzevaadom/actions/workflows/hacs-validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/dn5qMDW3/tzevaadom?style=flat-square)](https://github.com/dn5qMDW3/tzevaadom/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz)

[English](README.md)

אינטגרציה מותאמת ל-Home Assistant למערכת ההתרעה של פיקוד העורף. מספקת התרעות בזמן אמת על ירי רקטות, התרעות מקדימות, חדירת כלי טיס עוינים, רעידות אדמה ועוד.

## מקורות נתונים

| מקור | כיסוי | הערות |
|------|-------|-------|
| **צופר** (tzevaadom.co.il) | עולמי | ללא הגדרות נוספות. מומלץ למשתמשים מחוץ לישראל. |
| **פיקוד העורף ישיר** (oref.org.il) | ישראל בלבד | חיבור ישיר ל-API של פיקוד העורף. |
| **פיקוד העורף דרך Proxy** | עולמי | באמצעות שרת Proxy שלכם לגישה ל-API. |

## תכונות

- **התרעות בזמן אמת** — סריקה כל 2-3 שניות (ניתן להגדרה)
- **חיישן התרעה מקדימה** — חיישן בינארי נפרד להתרעות מקדימות
- **זיהוי סיום אירוע** — חיישן ההתרעה מתאפס מיד כשפיקוד העורף מפרסם "האירוע הסתיים"
- **סינון לפי מיקום** — ניטור מחוזות או ישובים ספציפיים
- **סינון לפי קטגוריה** — בחירת סוגי התרעות (רקטות, כטמ"מ, רעידות אדמה ועוד)
- **חיישנים לפי קטגוריה** — חיישן בינארי נפרד לכל סוג התרעה
- **היסטוריית התרעות** — חיישן עם עד 24 שעות היסטוריית התרעות מה-API
- **חיישן ארצי** — חיישנים אופציונליים לכל ההתרעות בישראל (ללא סינון)
- **מונע אירועים** — שליחת אירועי `tzevaadom_alert`, `tzevaadom_early_warning` ו-`tzevaadom_all_clear` לאוטומציות
- **תבניות מובנות** — תבניות אוטומציה מוכנות לשימוש להתראות, תאורה ו-TTS
- **עדכון אוטומטי** — רשימות מחוזות/ישובים מתעדכנות אוטומטית
- **דו-לשוני** — תמיכה מלאה בעברית ובאנגלית
- **אבחון** — כלי אבחון מובנה לפתרון בעיות
- **תואם HACS** — התקנה קלה דרך HACS

## התקנה

### HACS (מומלץ)

1. פתחו את HACS ב-Home Assistant
2. לחצו על תפריט שלוש הנקודות > **Custom repositories**
3. הוסיפו `https://github.com/dn5qMDW3/tzevaadom` עם קטגוריה **Integration**
4. לחצו **Install**
5. הפעילו מחדש את Home Assistant

### ידני

1. העתיקו את תיקיית `custom_components/tzevaadom` לתיקיית `config/custom_components/`
2. הפעילו מחדש את Home Assistant

## הגדרה

1. היכנסו ל**הגדרות** > **מכשירים ושירותים** > **הוסף אינטגרציה**
2. חפשו **Tzeva Adom**
3. עקבו אחר אשף ההגדרה:
   - **מקור נתונים** — בחרו בין צופר (עולמי), פיקוד העורף ישיר (ישראל), או פיקוד העורף דרך Proxy
   - **סינון מיקום** — בחרו מחוזות ו/או ישובים (השאירו ריק לניטור ארצי)
   - **קטגוריות** — בחרו סוגי התרעות (השאירו ריק לכל הקטגוריות)
   - **הגדרות** — הגדירו תדירות סריקה וחיישן ארצי

## ישויות

### חיישנים בינאריים

| ישות | תיאור |
|------|-------|
| `binary_sensor.tzeva_adom_alert` | פועל כשיש התרעה התואמת את הסינון שלכם |
| `binary_sensor.tzeva_adom_alert_all` | פועל כשיש התרעה ארצית כלשהי (אופציונלי) |
| `binary_sensor.tzeva_adom_early_warning` | פועל כשיש התרעה מקדימה באזורים שלכם |
| `binary_sensor.tzeva_adom_alert_cat_1` | פועל בהתרעת ירי רקטות וטילים |
| `binary_sensor.tzeva_adom_alert_cat_6` | פועל בהתרעת חדירת כלי טיס עוין |
| `binary_sensor.tzeva_adom_alert_cat_*` | חיישנים לפי קטגוריה לכל סוגי ההתרעות (מושבתים כברירת מחדל) |

**תכונות התרעה**: `alert_id`, `category`, `category_name_he`, `category_name_en`, `title`, `description`, `cities`, `cities_count`, `alert_count`, `is_drill`, `priority`, `shelter_time`

**תכונות התרעה מקדימה**: `alert_count`, `cities`, `title`, `description`

### חיישנים

| ישות | תיאור |
|------|-------|
| `sensor.tzeva_adom_last_alert` | פרטי ההתרעה האחרונה |
| `sensor.tzeva_adom_alert_type` | קטגוריית ההתרעה הפעילה (מסונן) |
| `sensor.tzeva_adom_alert_type_nationwide` | קטגוריית ההתרעה הפעילה (ארצי, אופציונלי) |
| `sensor.tzeva_adom_alerts_history` | היסטוריית התרעות אחרונות עם חותמות זמן (מסונן) |
| `sensor.tzeva_adom_alerts_history_nationwide` | היסטוריית התרעות (ארצי, אופציונלי) |

**תכונות התרעה אחרונה**: `alert_id`, `category`, `category_name_he`, `category_name_en`, `title`, `description`, `cities`, `is_drill`, `priority`, `shelter_time`, `time_in_shelter_seconds`

**תכונות סוג התרעה**: `category_id`, `category_name_he`, `category_name_en`, `is_drill`, `priority`, `active_categories`, `cities_count`, `shelter_time`

**היסטוריית התרעות**: המצב הוא מספר ההתרעות. רשומות ההיסטוריה נמצאות בתכונה `entries` עם חותמות זמן, קטגוריות וישובים.

## תבניות (Blueprints)

האינטגרציה כוללת תבניות אוטומציה מוכנות לשימוש, זמינות אוטומטית תחת **הגדרות** > **אוטומציות** > **תבניות**:

| תבנית | תיאור |
|-------|-------|
| **התראה לנייד** | שליחת התראה לנייד עם פרטי ההתרעה, ישובים וזמן מיגון. תומך בהתראות קריטיות ב-iOS. |
| **הבהוב תאורה בהתרעה** | הבהוב תאורה בזמן התרעה עם צבע לפי קטגוריה (אדום=רקטות, כתום=כטמ"מ, צהוב=רעידת אדמה). שחזור מצב קודם בסיום. |
| **הכרזת TTS** | הכרזה קולית על פרטי ההתרעה דרך נגן מדיה. |

## שירותים

| שירות | תיאור |
|-------|-------|
| `tzevaadom.force_refresh` | רענון נתונים מיידי |

## אירועים

### `tzevaadom_alert`

נשלח עבור כל התרעה חדשה התואמת את הסינון:

```yaml
event_type: tzevaadom_alert
data:
  id: "133456789"
  cat: 1
  title: "ירי רקטות וטילים"
  desc: "היכנסו למרחב המוגן..."
  cities:
    - "תל אביב - מרכז העיר"
    - "חולון"
  is_drill: false
  category_name_he: "ירי רקטות וטילים"
  category_name_en: "Rockets and Missiles"
  priority: 120
  shelter_time: 15
```

### `tzevaadom_all_clear`

נשלח כשישובים יוצאים מהתרעה (סיום אירוע):

```yaml
event_type: tzevaadom_all_clear
data:
  cities:
    - "תל אביב - מרכז העיר"
    - "חולון"
  cities_count: 2
```

### `tzevaadom_early_warning`

נשלח כשמזוהות התרעות מקדימות באזורים שלכם:

```yaml
event_type: tzevaadom_early_warning
data:
  id: "133456790"
  cat: 1
  title: "התרעה מקדימה"
  desc: "..."
  cities:
    - "אשדוד"
  is_drill: false
  category_name_he: "ירי רקטות וטילים"
  category_name_en: "Rockets and Missiles"
  priority: 120
```

## דוגמאות אוטומציה

### התראה על התרעה

```yaml
automation:
  - alias: "התראת צבע אדום"
    trigger:
      - platform: event
        event_type: tzevaadom_alert
    action:
      - service: notify.mobile_app
        data:
          title: "{{ trigger.event.data.title }}"
          message: "אזורים: {{ trigger.event.data.cities | join(', ') }}"
```

### התרעה מקדימה — הכנת מיגון

```yaml
automation:
  - alias: "התרעה מקדימה - היערכות"
    trigger:
      - platform: event
        event_type: tzevaadom_early_warning
    action:
      - service: notify.mobile_app
        data:
          title: "התרעה מקדימה"
          message: "התכוננו למיגון: {{ trigger.event.data.cities | join(', ') }}"
```

### הבהוב אורות בהתרעה

```yaml
automation:
  - alias: "הבהוב אורות בהתרעה"
    trigger:
      - platform: state
        entity_id: binary_sensor.tzeva_adom_alert
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          color_name: red
          brightness: 255
```

## קטגוריות התרעה

| מזהה | עברית | אנגלית |
|------|-------|--------|
| 1 | ירי רקטות וטילים | Rockets and Missiles |
| 2 | ירי לא קונבנציונלי | Non-conventional Missiles |
| 3 | רעידת אדמה | Earthquake |
| 4 | אירוע רדיולוגי | Radiological Event |
| 5 | צונאמי | Tsunami |
| 6 | חדירת כלי טיס עוין | Hostile Aircraft Intrusion |
| 7 | חומרים מסוכנים | Hazardous Materials |
| 8 | אזהרה | Warning |
| 13 | חדירת מחבלים | Terrorist Infiltration |
| 101+ | תרגילים | Drills (מזהה קטגוריה אמיתי + 100) |

## הקטנת נפח מסד הנתונים

חיישני ההיסטוריה שומרים עד 500 רשומות התרעה בתכונות שלהם. אם מסד הנתונים של Home Assistant גדל יותר מדי, ניתן לא לכלול חיישנים אלו מה-recorder:

```yaml
# configuration.yaml
recorder:
  exclude:
    entity_globs:
      - sensor.tzeva_adom_alerts_history*
```

## מופעים מרובים

ניתן להוסיף את האינטגרציה מספר פעמים עם סינונים שונים ליצירת קבוצות ניטור נפרדות (למשל: בית מול משרד).

## אבחון

לפתרון בעיות, היכנסו ל**הגדרות** > **מכשירים ושירותים** > **Tzeva Adom** > **תפריט 3 נקודות** > **הורד אבחון**. מידע רגיש (כתובות Proxy) מוסתר אוטומטית.

## רישיון

MIT

</div>
