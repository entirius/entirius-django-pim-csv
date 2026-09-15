---
title: CSV Format Specification
description: Column definitions, naming conventions, and examples for all PIM CSV import files.
---

All CSV files use comma (`,`) as separator, minimal quoting, and UTF-8 encoding. Open with LibreOffice Calc (comma separator only) — Excel often corrupts the format.

## File Naming

Full import files follow a strict naming convention:

```
[ENTITY]--[SCOPE].csv
```

Update files include a timestamp and description:

```
[ENTITY]-update--[SCOPE]--[DATETIME]--[SUFFIX].csv
```

Where:
- `ENTITY` — object type (`categories`, `products`, `attributes`, `pricelist`, `qty`)
- `SCOPE` — shop_idx, feature_idx, sale_channel_idx, or storage_code
- `DATETIME` — `2023-01-01-23-59` format
- `SUFFIX` — short description (e.g., `desc-de`, `prices-q4`)

## Translation Columns

Translated fields have one column per language, using the pattern `{field} {lang}`:

```
name en, name pl, name de
short_description en, short_description pl
url_key en, url_key pl
```

The default language column is required. Other languages are optional — missing values preserve existing translations.

---

## Categories

**File:** `categories--{shop_idx}.csv`
**Command:** `categories-import-from-csv {shop_idx} {file}`

### Columns

| Column | Required | Description |
|--------|----------|-------------|
| `idx` | yes | Unique category identifier (slugified, lowercase) |
| `parent` | yes | Parent category idx (empty for root categories) |
| `is_enabled` | no | Active status (`1`/`0`, `true`/`false`, `yes`/`no`) |
| `name {lang}` | yes (default lang) | Category name per language |
| `url_key {lang}` | no | URL slug per language |
| `description {lang}` | no | Category description per language |
| `meta_title {lang}` | no | SEO meta title per language |
| `meta_description {lang}` | no | SEO meta description per language |
| `img_main` | no | Category image path or URL |
| `extension_json` | no | Custom JSON data |

### Example

```csv
idx,parent,is_enabled,name en,name pl,url_key en,url_key pl
furniture,,1,Furniture,Meble,furniture,meble
chairs,furniture,1,Chairs,Krzesla,chairs,krzesla
tables,furniture,1,Tables,Stoly,tables,stoly
```

### Notes

- Categories are sorted by tree depth before import — parents are always created first.
- The `idx` must be unique within a shop but can repeat across shops.
- Category separators: both `,` and `;` are supported in multi-category fields.

---

## Products

**File:** `products--{shop_idx}.csv`
**Command:** `products-import-from-csv {shop_idx} {file}`

### Core Columns

| Column | Required | Description |
|--------|----------|-------------|
| `sku` | yes | Unique product identifier |
| `product_type` | no | `simple` (default), `config`, `bundle`, `virtual` |
| `feature_set` | no | Feature set idx |
| `category` | no | Category idx (comma-separated for multiple) |
| `is_enabled` | no | Active status |
| `kind_of_product` | no | `physical` (default) or `virtual` |

### Translation Columns

| Column | Required | Description |
|--------|----------|-------------|
| `name {lang}` | yes (default lang) | Product name |
| `short_description {lang}` | no | Short description |
| `description {lang}` | no | Full description |
| `url_key {lang}` | no | URL slug |
| `meta_title {lang}` | no | SEO meta title |
| `meta_description {lang}` | no | SEO meta description |

### Dimension Columns

| Column | Description |
|--------|-------------|
| `weight` | Product weight |
| `width` | Product width |
| `height` | Product height |
| `deep` | Product depth |

### Image Columns

| Column | Description |
|--------|-------------|
| `img_main` | Main product image (path or URL) |
| `img_1`, `img_2` | Additional gallery images |
| `images` | Comma-separated list of image paths |

### Link Columns

| Column | Description |
|--------|-------------|
| `linked_cross_sell` | Cross-sell product SKUs (comma-separated) |
| `linked_up_sell` | Up-sell product SKUs |
| `linked_related` | Related product SKUs |
| `linked_navigation` | Navigation link SKUs |

### File Columns

| Column | Description |
|--------|-------------|
| `files` | Downloadable file paths (semicolon-separated) |
| `files_categories` | File category labels |
| `files_labels` | File display labels |

### Configurable Product Columns

| Column | Description |
|--------|-------------|
| `config_features` | Features used for variants (semicolon-separated, e.g., `size;color`) |
| `config_sku` | Child product SKUs (comma-separated) |

### Bundle Product Columns

| Column | Description |
|--------|-------------|
| `bundle_sku` | Bundle components (comma-separated, see format below) |
| `bundle_idx` | Bundle section/title identifier |

**`bundle_sku` format:** `SKU;quantity;is_required;is_default;can_change_quantity`

Only `SKU;quantity` is required. The boolean flags are optional and default to: `is_required=false`, `is_default=false`, `can_change_quantity=true`. Boolean values accept: `true`, `1`, `yes`, `prawda`.

### Feature Columns

Feature values are added as dynamic columns named by their feature idx:

```csv
sku,color,size,brand
PROD-001,red,xl,acme
```

For translated features, use the `{feature} {lang}` pattern:

```csv
sku,material en,material pl
PROD-001,Cotton,Bawelna
```

### Example — Simple Products

```csv
sku,name en,name pl,category,color,size,img_main
SHIRT-001,Blue Shirt,Niebieska Koszula,clothing,blue,m,pictures/shirt-001.png
SHIRT-002,Red Shirt,Czerwona Koszula,clothing,red,l,pictures/shirt-002.png
```

### Example — Configurable Products

```csv
sku,product_type,name en,config_features,config_sku
SHIRT-CONFIG,config,Shirt,size;color,"SHIRT-001,SHIRT-002,SHIRT-003"
SHIRT-001,simple,Blue Shirt M,,,
SHIRT-002,simple,Red Shirt L,,,
```

### Example — Bundle Products

```csv
sku,product_type,name en,bundle_sku,bundle_idx
BUNDLE-001,bundle,Starter Kit,"ITEM-A;2,ITEM-B;1,ITEM-C;4",starter-bundle
```

With extension fields (is_required, is_default, can_change_quantity):

```csv
sku,product_type,name en,bundle_sku,bundle_idx
BUNDLE-002,bundle,Premium Kit,"ITEM-A;2;true;true;false,ITEM-B;1;false;false;true",premium-bundle
```

The separator between fields is configurable via `BUNDLE_SKU_QUANTITY_SEPARATOR` (default: `;`).

### Visibility Values

The `visibility` column accepts:

| Value | Meaning |
|-------|---------|
| `not visible individually` | Hidden from search and catalog |
| `catalog` | Visible in catalog only |
| `search` | Visible in search only |
| `catalog, search` | Visible everywhere |

---

## Attributes

**File:** `attributes--{feature_idx}.csv`
**Command:** `attributes-import-from-csv {feature_idx} {file}`

| Column | Required | Description |
|--------|----------|-------------|
| `idx` | yes | Attribute identifier (min 3 characters, slugified) |
| `name {lang}` | yes (default lang) | Attribute display name per language |
| `description {lang}` | no | Attribute description per language |
| `extension_json` | no | Custom JSON (e.g., color hex: `{"type":"color","value":"#FF0000"}`) |
| `image` | no | Attribute swatch image path |
| `display_order` | no | Sort position |
| `group` | no | Attribute group identifier |

### Example

```csv
idx,name en,name pl,extension_json
red,Red,Czerwony,"{""type"":""color"",""value"":""#FF0000""}"
blue,Blue,Niebieski,"{""type"":""color"",""value"":""#0000FF""}"
green,Green,Zielony,"{""type"":""color"",""value"":""#00FF00""}"
```

---

## Product Positions

**File:** `products-position--{shop_idx}.csv`
**Command:** `products-position-import-from-csv {shop_idx} {file}`

| Column | Required | Description |
|--------|----------|-------------|
| `sku` | yes | Product SKU |
| `category` | yes | Category idx |
| `position` | yes | Display position (integer) |

---

## Prices

**File:** `pricelist--{sale_channel_idx}.csv`
**Command:** `import-pricelist-from-csv {sale_channel_idx} {file}`

Managed by django-price-manager, not django-pim-csv. The sale channel must have "Price source" set to "csv" in Django Admin.

| Column | Description |
|--------|-------------|
| `sku` | Product SKU |
| `price` | Regular price |
| `special_price` | Sale price (optional) |

---

## Quantities

**File:** `qty--{storage_code}.csv`
**Command:** `qms-manage-quantities`

Managed by django-qms, not django-pim-csv. Configure the CSV path in Django Admin:

```json
{"csv_path": "%IMPORT_DIR%/qty.csv"}
```

| Column | Description |
|--------|-------------|
| `sku` | Product SKU |
| `qty` | Stock quantity |

---

## Cynthia Visibility

Controls product/category active status in the storefront.

**Files:**
- `products-status--{channel_idx}.csv`
- `categories-status--{channel_idx}.csv`

**Commands:**
- `import-product-representation-from-csv --filepath={file}`
- `import-product-category-representation-from-csv --filepath={file}`

### Products Status

| Column | Description |
|--------|-------------|
| `sku` | Product SKU |
| `enabled` | Active status (`1`/`0`) |
| `channel` | Channel idx |

### Categories Status

| Column | Description |
|--------|-------------|
| `idx` | Category idx |
| `is_active` | Active status (`1`/`0`) |
| `channel` | Channel idx |

---

## Decimal Parsing

The importer handles multiple numeric formats:

| Input | Parsed as |
|-------|-----------|
| `14 000,45` | `14000.45` |
| `39.000000` | `39.00` |
| `17,5` | `17.50` |
| `100` | `100.00` |

## Boolean Parsing

These values are recognized as `True`: `yes`, `true`, `1`, `prawda`. Everything else is `False`.
