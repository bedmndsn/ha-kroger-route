# Kroger Route Planner

A Home Assistant custom integration that syncs a `todo` shopping list with the
Kroger Product API, sorts items into an optimal walking route through your
store, and exposes the result as a sensor you can display on any dashboard.

Works with all Kroger-family banners (Kroger, Ralphs, Fry's, King Soopers, QFC,
Fred Meyer, Smith's, Dillons, Harris Teeter, etc.) as long as your store location
supports product search.

## Features

- Config Flow UI: enter your Kroger API credentials, search for your store by
  ZIP code, and pick which `todo` list to sync — no YAML required.
- Options Flow UI: switch between built-in store layout presets or define
  your own custom aisle/department order at any time.
- Multi-store support: add more than one store; each gets its own sensor with
  a unique entity ID, so entities never collide.
- Handles Kroger's WAF (adds browser-like headers to avoid 403s) and its
  `PRODUCT-2029` "product search not available at this location" error.
- Standalone `harvest_aisle_data.py` script for sampling how a given store
  describes its aisles, useful when tuning a custom layout.

## Installation (HACS)

1. In HACS, choose **Custom repositories**, add this repository URL, and
   select category **Integration**.
2. Install **Kroger Route Planner** from HACS and restart Home
   Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for
   \"Kroger Route Planner\".

## Setup

1. **Kroger API Credentials** — Enter the `Client ID` and `Client Secret`
   from your app at [developer.kroger.com](https://developer.kroger.com).
   These are validated against Kroger's OAuth endpoint immediately.
2. **Select Home Store** — Enter your ZIP code to search nearby stores, then
   pick your store from the dropdown. The store is validated to make sure it
   actually supports product search before you can continue.
3. **Select Shopping List** — Pick the `todo.*` entity that holds your
   grocery list (defaults to `todo.shopping_list`).

After setup, a sensor named `Kroger Route (<Store Name>)` is created with entity ID
`sensor.kroger_route_<location_id>` (e.g. `sensor.kroger_route_01400123`). Existing
installs keep their previous entity ID (`sensor.kroger_shopping_route`) via Home
Assistant's entity registry.

## Options

From the integration's entry in **Settings > Devices & Services**, click
**Configure** to customize list behavior at any time:

- **Target To-Do Entity** — Change the target `todo` list entity.
- **Store Layout Preset** — Choose between `standard_right`, `standard_left`, `marketplace`, `perimeter_first`, `cold_chain_last`, or `urban_compact`.
- **Custom Layout** — Or select `custom` and enter your own comma-separated department order (e.g. `PRODUCE, DAIRY, AISLES_1_3, DELI, AISLES_4_17, MEAT, AISLE_18, BAKERY, AISLES_19_PLUS, FRONT_END, UNSORTED`).
- **Ignore Items (Case-Insensitive)** — Headers and noise phrases to filter out from your list, one per line (e.g. `shopping list`, `kroger`, `ralphs`, `groceries`). Matching is completely case-insensitive.
- **Typo / Brand Corrections (Case-Insensitive)** — Auto-correct voice/OCR input (format: `wrong = correct`). For example: `yogrt = yogurt` or `oj = orange juice`.
- **Direct Product IDs / UPCs** — Bypass keyword search for tricky items with an exact 13-digit Kroger Product ID / UPC (format: `item = productId`). For example: `maple syrup = 0001111050123`.
- **Proxy URL** — Optional HTTP/SOCKS5 proxy for development or troubleshooting.

## Services

- `kroger_route.refresh_route` — Immediately re-fetch the shopping list and
  rebuild the walking route, instead of waiting for the next scheduled poll.

## Sensor Attributes

`sensor.kroger_route_01400123` exposes:

```json
{
  "items": [
    {
      "name": "bread",
      "product_title": "Private Selection Whole Wheat Bread",
      "aisle": "Aisle 02",
      "price": 2.99,
      "image": "https://...",
      "completed": false
    }
  ],
  "total_estimated_cost": 3.49,
  "location_id": "01400123",
  "todo_entity": "todo.shopping_list",
  "preset_used": "standard_right"
}
```

## Display Options

### Option 1: Custom Interactive In-Store Card (Recommended)
This card gives you an interactive, real-time checklist right inside your Home Assistant dashboard. Tapping an item marks it completed immediately in the UI (with strike-through styling) and syncs the status directly to your Home Assistant To-Do list (`todo.shopping_list`). It also shows official product thumbnail photos, prices, aisle headers, and estimated cart total.

**Prerequisite:** Install [html-template-card](https://github.com/Parnassius/html-template-card) via HACS (**HACS → Frontend → HTML Template Card**).

```yaml
type: custom:html-template-card
title: 🛒 Kroger Route Planner
ignore_line_breaks: true
entities:
  - sensor.kroger_route_01400123
content: |
  {% set route = state_attr('sensor.kroger_route_01400123', 'items') %}
  {% set total = state_attr('sensor.kroger_route_01400123', 'total_estimated_cost') %}

  {% if route and route | length > 0 %}
    <div style="font-size: 20px; font-weight: bold; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid var(--divider-color);">
      💳 Est. Total: ${{ total }}
    </div>

    {% set current_aisle = namespace(value="") %}
    {% for item in route %}
      
      {% if item.aisle != current_aisle.value %}
        {% set current_aisle.value = item.aisle %}
        <div style="color: var(--primary-color); font-weight: bold; font-size: 18px; margin-top: 28px; margin-bottom: 12px; padding-bottom: 4px; border-bottom: 1px solid rgba(150, 150, 150, 0.2);">
          📍 {{ item.aisle | upper }}
        </div>
      {% endif %}
      
      <div id="row-{{ loop.index }}" style="display: flex; align-items: center; justify-content: space-between; padding: 16px 0; border-bottom: 1px solid rgba(150,150,150,0.1); transition: opacity 0.2s ease; opacity: {{ '0.4' if item.status == 'completed' else '1' }};">
        
        <div style="display: flex; align-items: center; gap: 16px; flex-grow: 1;">
          
          <div 
            onclick="
              const card = this.closest('html-template-card');
              const isDone = '{{ item.status }}' === 'completed';
              const nextStatus = isDone ? 'needs_action' : 'completed';
              
              /* Immediate Client-Side Visual Feedback */
              this.innerHTML = isDone ? '' : '✔'; 
              this.style.backgroundColor = isDone ? 'transparent' : 'var(--primary-color)'; 
              this.style.color = isDone ? 'transparent' : 'white';
              
              card.querySelector('#row-{{ loop.index }}').style.opacity = isDone ? '1' : '0.4';
              card.querySelector('#text-{{ loop.index }}').style.textDecoration = isDone ? 'none' : 'line-through';
              
              /* Background Home Assistant Sync Using UID */
              card._hass.callService('todo', 'update_item', {entity_id: 'todo.shopping_list', item: '{{ item.uid }}', status: nextStatus});
            "
            style="width: 32px; height: 32px; border: 2px solid var(--primary-color); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; font-size: 18px; transition: all 0.2s ease; background-color: {{ 'var(--primary-color)' if item.status == 'completed' else 'transparent' }}; color: {{ 'white' if item.status == 'completed' else 'transparent' }};"
          >{{ '✔' if item.status == 'completed' else '' }}</div>
          
          {% if item.image_url %}
            <img src="{{ item.image_url }}" style="width: 64px; height: 64px; object-fit: contain; border-radius: 8px; background: white; padding: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.15); flex-shrink: 0;">
          {% else %}
            <div style="width: 64px; height: 64px; border-radius: 8px; background: var(--secondary-background-color); display: flex; align-items: center; justify-content: center; font-size: 28px; flex-shrink: 0;">🛒</div>
          {% endif %}
          
          <div style="display: flex; flex-direction: column;">
            <span id="text-{{ loop.index }}" style="font-weight: bold; font-size: 18px; color: var(--primary-text-color); transition: all 0.2s ease; text-decoration: {{ 'line-through' if item.status == 'completed' else 'none' }};">{{ item.name }}</span>
            {% if item.product_name and item.product_name != item.name %}
              <span style="font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; line-height: 1.2;">↳ {{ item.product_name }}</span>
            {% endif %}
          </div>
        </div>

        {% if item.price > 0 %}
          <div style="font-weight: bold; font-size: 16px; color: var(--primary-text-color); opacity: 0.9; margin-left: 12px; flex-shrink: 0;">
            ${{ item.price }}
          </div>
        {% endif %}

      </div>
    {% endfor %}

  {% else %}
    <div style="text-align: center; padding: 40px; color: var(--secondary-text-color);">
      <ha-icon icon="mdi:cart-outline" style="--mdc-icon-size: 64px; opacity: 0.5; margin-bottom: 16px;"></ha-icon>
      <br><em style="font-size: 18px;">Your shopping list is clear!</em>
    </div>
  {% endif %}

  <div style="text-align: center; margin-top: 24px; padding-top: 12px; border-top: 1px dashed rgba(150,150,150,0.2);">
    <button 
      onclick="
        const btn = this;
        btn.style.opacity = '0.5';
        btn.innerText = '⟳ Refreshing Route...';
        this.closest('html-template-card')._hass.callService('kroger_route', 'refresh_route', {});
        setTimeout(() => { btn.style.opacity = '1'; btn.innerText = '⟳ Refresh Route'; }, 2000);
      "
      style="background: transparent; border: 1px solid var(--divider-color); color: var(--secondary-text-color); padding: 6px 14px; border-radius: 20px; font-size: 13px; cursor: pointer; transition: all 0.2s ease;"
    >⟳ Refresh Route</button>
  </div>
```


### Option 2: Native Markdown Card (Zero Plugins Required)

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: 🛒 Kroger Route Planner
    content: >-
      {% set items = state_attr('sensor.kroger_route_01400123', 'items') %}
      {% if items %}
        {% for item in items %}
          **{{ item.aisle }}**: {{ item.name }} _(${{ item.price }})_
        {% endfor %}
      {% else %}
        _No active items on your shopping list!_
      {% endif %}
  - type: button
    name: Refresh Route
    icon: mdi:refresh
    tap_action:
      action: perform-action
      perform_action: kroger_route.refresh_route
```

### Option 3: Geofenced Mobile Push Notification Automation

```yaml
alias: "Kroger Route: Push Notification on Arrival"
trigger:
  - platform: zone
    entity_id: device_tracker.your_iphone
    zone: zone.grocery_store
    event: enter
action:
  - action: notify.mobile_app_your_iphone
    data:
      title: "🛒 Kroger Route Planner"
      message: >-
        {% set items = state_attr('sensor.kroger_route_01400123', 'items') %}
        {% for item in items %}
        • {{ item.aisle }}: {{ item.name }}
        {% endfor %}
```

## iOS Integration: Siri, Reminders Sync & OCR Scanner

You can populate your Home Assistant shopping list completely hands-free using Apple Reminders and Siri, or digitize handwritten lists in seconds using an OCR Shortcut.

### 1. Apple Reminders & Siri Voice Sync

By syncing an Apple Reminders list with Home Assistant's `todo` entity via the **Home Assistant iOS Companion App**, any item added via Siri or the Reminders app instantly syncs into Home Assistant.

#### How It Works:
- **Companion App Sync**: In the Home Assistant Companion App on iOS, navigate to **Settings > Companion App > To-Do Lists / Reminders** (or enable Apple Reminders list sync). Map your Apple Reminders list (e.g. `Groceries`) to your Home Assistant To-Do entity (`todo.shopping_list`).
- **Siri Voice Input**: Trigger Siri on iPhone, Apple Watch, HomePod, or CarPlay:
  - *"Hey Siri, add bread to my groceries list."*
  - Alternatively, if you set `Groceries` as your default list in iOS under **Settings > Reminders > Default List**, you can simply say:
    *"Hey Siri, add milk to my shopping list."*
- **Seamless Route Building**: Items added via Siri sync directly into `todo.shopping_list`. The Kroger Route Planner integration automatically fetches them, deduplicates entries, and sorts them into your optimized walking route with prices, aisle numbers, and product photos.

---

### 2. Handwritten List OCR Ingest Shortcut ("Scan List To Grocery list")

If you write grocery lists by hand or use stationery notepads, this iOS Shortcut lets you snap a photo, clean up spelling errors and split items using ChatGPT, and batch-import them directly into your Reminders `Groceries` list (which syncs immediately to Home Assistant).

```
[Camera: Take Photo] ➔ [Extract Text (iOS OCR)] ➔ [Ask ChatGPT: Clean & Split] ➔ [Add Each Line to Reminders: Groceries] ➔ [HA Companion Sync] ➔ [todo.shopping_list] ➔ [Kroger Route Planner]
```

#### Step-by-Step Shortcut Recipe:

1. **Take `1 photo` with `Back` camera**
2. **Extract `Text` from `Photo`** (uses native iOS Vision OCR)
3. **Ask ChatGPT** with a prompt configured to clean and normalize OCR output:
   ```text
   The following is a messy OCR scan of a handwritten grocery list. Please fix obvious spelling errors (e.g. 'Bannana' to 'Banana' or 'Chiken' to 'Chicken'), separate any items that got merged into the same line, and ignore stationery headers with lines or boxes around them (e.g. 'Groceries', 'Kroger', or 'Shopping List'). Output the final list with one item per line, with no bullet points or extra text. "[Extracted Text]"
   ```
4. **Split `Ask ChatGPT` by `New Lines`**
5. **Repeat with each item in `Split Text`**:
   - **Add `Repeat Item` to `Groceries` with `No Alert`**
6. **End Repeat**

#### Why This Works Seamlessly with Kroger Route Planner:
- **Intelligent Pre-processing**: ChatGPT strips stationery headers (e.g., "Groceries", "Shopping List", "To Buy"), separates merged multi-line entries, and standardizes handwriting before items hit Reminders.
- **Hands-Off Ingestion**: Once the items are added to Reminders, the Home Assistant Companion App pushes them to `todo.shopping_list` without manual intervention or webhooks.
- **Built-In Deduplication & Mappings**: Even if items are slightly misspelled or duplicated during scanning, Kroger Route Planner automatically purges duplicates and applies your configured typo corrections before routing.

## Store Layout Presets

Most Kroger banner supermarkets (Kroger, Ralphs, Fry's, King Soopers, QFC, Fred Meyer, Smith's, Dillons, Harris Teeter) share common architectural floor plans. You can select any of these curated presets directly from the Configure menu:

1. **Right Entrance (Standard Grocery)** — The most common grocery layout nationwide. Enter on the right into Produce & Floral, pass the Deli/Bakery, walk ascending center grocery aisles (1–N), fresh Meat & Seafood along the back perimeter, Dairy on the far wall, and Frozen before checkout.
2. **Left Entrance (Inverted / Mirror Layout)** — For stores with the entrance on the left. Produce and Bakery on the left, center grocery aisles, Meat & Seafood along the back, Dairy on the right wall, and Frozen.
3. **Kroger Marketplace & Mega-Stores** — Tailored for large 30–80 aisle superstores. Early dry grocery and pantry aisles (1–20) precede the rear fresh wall (Meat/Seafood/Dairy), followed by high-number aisles (Frozen, Paper/Chemical, Pet, General Merchandise).
4. **Perimeter First (Fresh Ring)** — Outer fresh loop first. Walk the complete outer perimeter for fresh whole foods (Produce → Deli → Seafood → Meat → Dairy) before navigating the interior grocery aisles.
5. **Cold Chain Last** — Keeps all refrigerated and frozen goods until the very end of your route so ice cream, dairy, and cold foods don't warm up during long trips or in hot climates.
6. **Urban Compact / Interleaved** — Tailored for dense urban grocery stores where fresh and refrigerated departments interleave with numbered center aisles (Produce → Dairy → Aisles 1–3 → Deli/Seafood → Aisles 4–17 → Packaged Meat → Bakery → Aisles 19+).
7. **Custom** — Build your own exact sequence using department names, general `NUMERIC_AISLES`, or explicit aisle ranges (e.g. `AISLES_1_10`, `AISLE_11`, `AISLES_12_PLUS`).

## Data Harvesting Helper (Optional)

`harvest_aisle_data.py` (repo root) is a standalone developer tool for sampling how a new or non-standard store describes its aisles, if you ever want to analyze a completely unique floor plan. It is strictly optional; the built-in presets cover the vast majority of store layouts out of the box.

## Known Limitations

- Some valid Kroger location IDs return `PRODUCT-2029` and don't support product search at all; the config flow will detect and reject these during store selection so you can pick an active location.

## Transparency & Development Disclosure

This project was architected, developed, and maintained with the assistance of **[Warp](https://www.warp.dev)** AI agents (Oz) for automated refactoring, integration design, documentation, and testing.
