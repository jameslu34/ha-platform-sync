# Cross-Platform Device Sync: Complete User Guide

> Applies to version: 0.6.5
> English name: Cross-Platform Device Sync
> Traditional Chinese name: 裝置平台同步

Cross-Platform Device Sync is a Home Assistant custom integration. It keeps a
chosen set of devices synchronized with Google Home, HomeKit, or Matterbridge.

This guide is written for everyday Home Assistant users. No programming
knowledge is required.

## Contents

1. [What this integration does](#what-this-integration-does)
2. [What to prepare](#what-to-prepare)
3. [Install the integration](#install-the-integration)
4. [First-time setup](#first-time-setup)
5. [Choose a synchronization source](#choose-a-synchronization-source)
6. [Choose target platforms](#choose-target-platforms)
7. [Use additions and exclusions](#use-additions-and-exclusions)
8. [Pause and re-enable synchronization](#pause-and-re-enable-synchronization)
9. [When synchronization runs](#when-synchronization-runs)
10. [Change your settings](#change-your-settings)
11. [Preview or synchronize now](#preview-or-synchronize-now)
12. [Plan per-platform safety rules](#plan-per-platform-safety-rules)
13. [Troubleshooting](#troubleshooting)
14. [Update or remove the integration](#update-or-remove-the-integration)
15. [Quick setup example](#quick-setup-example)

## What this integration does

The integration watches:

> **Which devices should appear on each smart-home platform.**

For example, you can:

- Use the devices shown on one or more Home Assistant dashboard views.
- Select a device list manually.
- Use the current device list from HomeKit, Google Home, or Matterbridge.
- Choose which of those devices should be sent to Google Home, HomeKit, or
  Matterbridge.

The integration compares the source with each selected target:

- If nothing changed, it does not run an unnecessary update.
- If a device was added, it adds that device to the selected targets.
- If a device was removed, it removes that device from the selected targets'
  shared device lists.
- Each target can have its own devices that are always included or always
  excluded.
- If an update fails, the integration attempts to restore the previous
  settings.

Each selected target converges to an exact set: `(source - exclusions) ∪
always-included devices`, followed by compatibility and protected rules. An
existing exposure is removed even if it predates this integration when it is
outside the final set. Unselected targets are left unchanged.

### What it does not do

The integration does not:

- Turn lights or switches on or off.
- Control locks, security systems, climate devices, cameras, or media playback.
- Resynchronize because a temperature, brightness, or other sensor value
  changed.
- Delete devices or entities from Home Assistant.
- Copy dashboard card designs or layouts to another platform.
- Create an extra sensor, button, or other Home Assistant entity.

It only manages whether a device is included in a target platform's shared
device list.

## What to prepare

Create a full Home Assistant backup before enabling synchronization for the
first time.

You only need to prepare the platforms that you plan to use:

| Platform | Before you begin |
|---|---|
| Google Home | Complete the Home Assistant Google Assistant integration and link the Google account |
| HomeKit | Create and pair the required HomeKit Bridge or Accessory in Home Assistant |
| Matterbridge | Install and start Matterbridge and its `matterbridge-hass` plugin |

If your source is a Home Assistant dashboard or a manually selected list, you
do not need to set up all three platforms. Prepare only the targets you select.

### Required Google Home target setup

When Google Home is a target, it needs a dedicated device configuration file.
The default file name is:

`google_assistant_entity_config.yaml`

Google Assistant must not expose every device by default. Merge these settings
into your existing Google Assistant configuration:

~~~yaml
google_assistant:
  expose_by_default: false
  entity_config: !include google_assistant_entity_config.yaml
~~~

Do not remove the other settings that your existing Google Assistant
configuration requires. If you are not comfortable editing YAML, ask your
Home Assistant administrator to complete this one-time setup.

### Required HomeKit setup

- When HomeKit is a source, create a working HomeKit Bridge or Accessory first.
- When HomeKit is a target, decide which HomeKit Bridges or Accessories this
  integration may update.
- Accessories paired directly in the Apple Home app do not appear in the
  HomeKit source list.

### Required Matterbridge setup

- Matterbridge must be running.
- `matterbridge-hass` must be installed, enabled, and connected to Home
  Assistant.
- Have the Matterbridge host name/IP address, or a complete secure management
  endpoint, and the management port available.
- If Matterbridge frontend authentication is enabled, have its password ready.
- The default management port is `8283`.

## Install the integration

### Recommended: install with HACS

The project uses a noncommercial source-available license, so install it as a
HACS custom repository rather than looking for it in the default HACS catalog.

1. Install and configure HACS if it is not already available.
2. Open **Custom repositories**, enter `jameslu34/ha-platform-sync` in the
   **Repository** field, and choose **Integration** as the category.
3. Find **Cross-Platform Device Sync** in HACS and select **Download**.
4. Create a Home Assistant backup.
5. Restart Home Assistant.

You can also use the **Open in HACS** button in the repository README to add the
custom repository.

### Manual installation

1. Download the latest GitHub release.
2. Copy the `custom_components/platform_sync` folder to
   `/config/custom_components/platform_sync`.
3. Confirm there is no extra directory level.
4. Create a Home Assistant backup.
5. Restart Home Assistant.

### Add the integration

1. Go to **Settings → Devices & services → Integrations**.
2. Select **Add integration**.
3. Search for:

   - English: **Cross-Platform Device Sync**
   - Traditional Chinese: **裝置平台同步**

4. Select the integration and begin setup.

Only one Cross-Platform Device Sync configuration is needed. If it is already
installed, open the existing configuration instead of adding another one.

## First-time setup

The setup wizard changes according to your choices. It only shows the fields
that are needed.

### Step 1: Choose a synchronization source

The first page contains:

- **Enable synchronization**: turns cross-platform synchronization on.
- **Synchronization source**: chooses the device list that acts as the source
  of truth.

If **Enable synchronization** is not selected, choosing **Next** immediately
finishes setup. No source details, targets, or connection settings are
requested.

### Step 2: Configure the source

The next page depends on the selected source:

| Synchronization source | What appears next |
|---|---|
| Devices on selected Home Assistant dashboard views | Select one or more dashboard views |
| Manually selected devices | Select entities directly |
| Devices in HomeKit | Select HomeKit Bridges and Accessories |
| Devices in Google Home | Continue directly to target selection |
| Devices in Matterbridge | Continue directly to target selection; connection settings appear later |

### Step 3: Choose target platforms

Select at least one target:

- Google Home
- HomeKit
- Matterbridge

### Step 4: Configure selected platforms

Only settings for selected targets are shown.

For example:

- If only Google Home is selected, HomeKit additions and exclusions do not
  appear.
- If only HomeKit is selected, the Google Assistant file field does not appear.
- If Matterbridge is the source, its host and port are still required even when
  it is not selected as a target.

### Step 5: Review settings

The final page shows:

- Whether synchronization is enabled
- The selected source
- The selected targets
- Selected dashboard views or HomeKit source entries

Review the summary and submit it. The integration does not change any target
platform before this final step is submitted.

## Choose a synchronization source

### Devices on selected Home Assistant dashboard views

Choose this source when you want the devices on selected dashboard views to
define what should appear on other platforms.

To set it up:

1. Choose **Devices on selected Home Assistant dashboard views**.
2. Select **Next**.
3. Select one or more dashboard views.
4. Select **Next** and choose the targets.

Devices from all selected views are combined. A device that appears on more
than one view is included only once.

If a view is not listed, choose the manual-path option and enter, for example:

- Dashboard URL path: `lovelace`
- Page URL path: `default-view`

Do not select listed dashboard views and the manual-path option at the same
time.

Keep in mind:

- Every selected view must remain readable.
- The selected views must contain at least one entity.
- The integration synchronizes the device list, not card appearance or order.

### Manually selected devices

Choose this source when you want complete control over a fixed device list.

To set it up:

1. Choose **Manually selected devices**.
2. Select **Next**.
3. Select one or more entities.
4. Select **Next** and choose the targets.

To add or remove a device later, return to the integration settings and edit
the list. Turning a device on or off does not change the list.

### Devices in Google Home

Choose this source when the device list currently shared by the Home Assistant
Google Assistant integration should be the source of truth.

There is no separate device-selection page. Setup continues directly to target
selection.

Keep in mind:

- The source is read from the Home Assistant Google Assistant integration.
- The integration does not sign in to the Google Home app to read its native
  device list.
- The Google Assistant integration must already be configured.

### Devices in HomeKit

The next page shows Home Assistant HomeKit Bridges and Accessories as a
checkbox list.

To set it up:

1. Select one or more HomeKit items to use as the source.
2. Select **Next** and choose the targets.

Keep in mind:

- You select a complete HomeKit Bridge or Accessory entry.
- You do not select every entity inside that entry on this page.
- This is not a list of accessories paired directly in the Apple Home app.
- If any selected item becomes unavailable, the integration stops that
  synchronization attempt instead of using an incomplete source.

Selecting a HomeKit item as a source is read-only. It does not give this
integration permission to update that item.

### Devices in Matterbridge

Choose this source when the existing Matterbridge device list should be the
source of truth.

Setup continues directly to target selection. Enter the Matterbridge host or
complete endpoint, port, and optional frontend password later on the
**Configure selected platforms** page.

Keep in mind:

- Matterbridge and `matterbridge-hass` must already be working.
- The integration reads Matterbridge's exact device list.
- It does not use Home Assistant labels to choose devices.

## Choose target platforms

### Google Home

When Google Home is selected, configure:

- **Google Assistant device configuration file**
- Optional **Always include in Google Home**
- Optional **Exclude from Google Home**

After a successful change, the integration asks Google Home to refresh its
device list.

### HomeKit

When HomeKit is selected, configure:

- **Managed HomeKit target entries**
- Optional **Always include in HomeKit**
- Optional **Exclude from HomeKit**

Only selected UI-managed HomeKit Bridges or Accessories may be updated.
Selecting a HomeKit entry as a source does not automatically make it a writable
target. For durable automatic updates, choose HomeKit entries created in the
Home Assistant UI. A YAML-managed item can still be used as a read-only source.
It may also stay in the managed target layout only as a fixed, exact
single-entity item in HomeKit Accessory mode; the writable main Bridge must be
UI-created. The integration will not rewrite an imported Accessory because
Home Assistant would restore it from YAML after a restart.

### Matterbridge

When Matterbridge is selected, configure:

- **Matterbridge host**
- **Matterbridge port**
- Optional **Matterbridge password**
- Optional **Always include in Matterbridge**
- Optional **Exclude from Matterbridge**

When a change is needed, the integration updates the device list and restarts
the `matterbridge-hass` plugin.

## Use additions and exclusions

Each selected target has its own exceptions.

Except for always-included devices and protected rules, every existing
exposure on a selected target that is absent from the source is removed.
Excluded devices stay absent even when they are in the source. Removal only
changes integration-managed exposure settings; it does not delete a Home
Assistant entity or remove a native platform pairing.

### Always include

Use this when a device should appear on one target even when it is not present
in the source.

Example:

- A virtual button should appear only in Google Home.
- Add it to **Always include in Google Home**.
- Do not add it to HomeKit or Matterbridge.

### Exclude

Use this when a device exists in the source but should not be sent to a
particular target.

Example:

- A dashboard contains a light that is already paired directly with HomeKit.
- Add it to **Exclude from HomeKit** to avoid a duplicate.
- The light can still be synchronized to Google Home or Matterbridge.

Keep in mind:

- The same entity cannot be both added and excluded on the same target.
- Each target has independent settings.
- Settings for an unselected target are not shown.
- Existing exceptions for an unselected target are kept and can be used again
  if that target is re-enabled later.

## Pause and re-enable synchronization

### Pause synchronization

1. Go to **Settings → Devices & services → Integrations**.
2. Find **Cross-Platform Device Sync**.
3. Select **Configure**.
4. Clear **Enable synchronization**.
5. Select **Next**.

The change is saved immediately.

While synchronization is off, the integration does not:

- Watch the source for changes
- Check the source on a schedule
- Run a startup scan
- Update any target platform

Your source, targets, and exception settings are kept.

Turning synchronization off does not undo the last synchronized device list.
Google Home, HomeKit, and Matterbridge keep the lists they had when
synchronization was paused.

### Re-enable synchronization

1. Open the integration settings again.
2. Select **Enable synchronization**.
3. Review the source and target pages.
4. Submit the final review page.

The integration runs one complete check after it is re-enabled and then
decides whether any platform needs an update.

## When synchronization runs

### After Home Assistant starts

When **Enable synchronization** is selected, a complete check always runs after
Home Assistant or the integration starts.

### When a dashboard source changes

Dashboard or related entity information changes normally trigger a check
quickly. Several changes made close together are combined to avoid repeated
updates.

### When a HomeKit source changes

The integration uses HomeKit configuration change notifications whenever
possible. If the installed Home Assistant version cannot provide those
notifications, the integration checks periodically instead.

Changes to an explicitly selected writable HomeKit target also wake an
immediate recheck. A platform that is still starting does not block saving the
completed settings; bounded background retries wait for it to converge.

### When Google Home or Matterbridge is the source

The integration checks the device list about every 15 seconds. Synchronization
starts only when it detects a change.

### Automatic Matterbridge recovery

While synchronization is enabled, background checks also verify that
Matterbridge, `matterbridge-hass`, the exact device list, and the loaded devices
are ready. For a narrowly defined runtime-only failure, the integration waits
until a Matterbridge backup has actually finished, restarts the Home Assistant
plugin first, and restarts the full Matterbridge process only when exact
readback still fails. A three-minute startup grace prevents normal plugin
warm-up from triggering a restart. It performs this recovery at most once per
failure episode and keeps a five-minute cooldown. Continued failures retry
after 15, 30, 60, 120, then 300 seconds.

The integration does not restart Matterbridge when the management interface is
unreachable, credentials are missing, the plugin is disabled, the exact list
is empty or different, or another filter is active. Disabling synchronization
also disables this automatic recovery.

### With a manual source

A manual source is not checked on a schedule. It is recalculated after you edit
the integration settings, restart the integration, or run synchronization
manually.

### When nothing changed

The integration records that no change is needed. It does not:

- Send another refresh request to Google Home
- Reload HomeKit
- Reload Matterbridge
- Control any device

## Change your settings

The integration does not create a settings entity. Open its configuration from:

**Settings → Devices & services → Integrations → Cross-Platform Device Sync →
Configure**

You can change:

- Whether synchronization is enabled
- The synchronization source
- Dashboard views or manually selected devices
- Target platforms
- Per-platform additions and exclusions
- The Google Assistant configuration file
- Managed HomeKit target entries
- Matterbridge connection settings

All saved settings are repopulated when you open **Configure** again. A
validation error keeps the other values you just entered. If you deselect a
target, its connection fields and additions/exclusions are hidden and inactive,
but remain saved and reappear when that target is selected again.

## Preview or synchronize now

Most users do not need these advanced actions during normal use.

### Preview synchronization

Go to **Developer tools → Actions** and choose:

`platform_sync.preview`

It shows the devices that would be added or removed without changing any
platform. Use it before a major settings change if you want to review the
result first.

### Synchronize now

Go to **Developer tools → Actions** and choose:

`platform_sync.sync_now`

It immediately checks the source and applies any required changes without
waiting for the next automatic check.

When **Enable synchronization** is off, neither action reads the source or
updates a target.

## Plan per-platform safety rules

Every home is different. Before enabling synchronization, identify devices that
must appear on only one platform and devices that are already paired natively.

For example, imagine these generic entities:

- `input_boolean.google_presence` should appear only in Google Home.
- `input_boolean.apple_presence` should appear only in HomeKit.
- `input_boolean.someone_arrived` should appear in Google Home and HomeKit but
  not Matterbridge.

Configure the example with independent target rules:

| Example entity | Google Home | HomeKit | Matterbridge |
|---|---:|---:|---:|
| `input_boolean.google_presence` | Always include | Exclude | Exclude |
| `input_boolean.apple_presence` | Exclude | Always include | Exclude |
| `input_boolean.someone_arrived` | Always include | Always include | Exclude |

These are examples, not built-in entities or default rules. Select your own
entities in each target's **Always include** and **Exclude** fields.

Also consider excluding the following from HomeKit targets:

- Devices already paired directly in Apple Home, to avoid duplicate
  accessories.
- Media devices supplied by Home Assistant's Apple TV integration when they are
  already available through their native Apple pairing.

Matterbridge uses an exact device list. The integration does not create or rely
on a special Home Assistant label for cross-platform selection.

## Troubleshooting

### Cross-Platform Device Sync does not appear

- Confirm that the folder is:
  `/config/custom_components/platform_sync`
- Make sure there is not an extra folder level.
- Restart Home Assistant after copying the files.
- Check the Home Assistant logs for a loading error.

### A dashboard view is missing

Some YAML dashboards or views that cannot be listed automatically do not
appear in the selection list. Choose the manual-path option and enter the
dashboard and page URL paths.

### The dashboard source is empty

- Confirm that every selected view still exists and opens normally.
- Confirm that the views contain at least one card with an entity.
- Confirm that all selected views are readable.

### A HomeKit source cannot be accepted or synchronized

- Confirm that you selected a Home Assistant HomeKit Bridge or Accessory.
- A temporarily unloaded entry can be saved, but synchronization waits until
  the HomeKit runtime is loaded and verifiably running.
- Confirm that it uses an explicit device list rather than a broad rule such as
  every device of a particular type.
- Accessories paired directly in Apple Home are not part of this source list.

### No writable HomeKit target is available

Create and pair a HomeKit Bridge or Accessory in Home Assistant first, then
return to this integration and select it. Cross-Platform Device Sync does not
create an Apple Home pairing for you.

If the main Bridge is YAML-managed, recreate it through the Home Assistant UI.
An imported single-entity item in Accessory mode may remain pinned in the
selected layout, but changing or removing it must be done in HomeKit YAML. The
integration will not apply a temporary imported-Accessory change that would
disappear after restart.

### Google Home setup is not ready

Check that:

- The Google Assistant integration is loaded.
- The Google account link is complete.
- `expose_by_default: false` is configured.
- A dedicated Google Assistant device configuration file is used.
- The file setting is a relative path, not a full disk path.

### Matterbridge cannot be reached

Check that:

- The host name, IP address, or full ws/wss/http/https endpoint is correct.
- The management port is correct.
- The optional frontend password is correct.
- A WSS endpoint has a certificate trusted by Home Assistant.
- Matterbridge is running.
- `matterbridge-hass` is enabled and connected to Home Assistant.

### Synchronization succeeded, but the mobile app has not changed

The integration can verify the Home Assistant side and the connected platform
configuration. The Google Home, Apple Home, or Matter controller app may still
need time to refresh.

If the device is still missing:

1. Wait briefly and reopen the app.
2. Confirm that the correct account, home, and Bridge pairing are in use.
3. Check the native app manually.

In this situation, Home Assistant-side synchronization is complete, but the
native app is not yet verified.

### Synchronization failed

1. Do not press **Synchronize now** repeatedly.
2. Open the integration settings and confirm that the source and selected
   targets are still available.
3. Run **Preview synchronization** first to review the planned changes.
4. Download diagnostics from the integration menu.
5. If recovery is reported as incomplete, use a Home Assistant or platform
   backup to restore the affected settings.

Before sharing diagnostics, check that they do not contain a password, token,
cookie, private key, or API key.

## Update or remove the integration

### Update

1. Turn **Enable synchronization** off temporarily.
2. Create a full Home Assistant backup.
3. Replace `custom_components/platform_sync` with the new version.
4. Restart Home Assistant.
5. Open the integration settings and review the source, targets, and
   exceptions.
6. Review every setting carefully, then re-enable synchronization. Submitting
   the final review page starts the automatic check.

Existing settings are migrated as safely as possible. Older versions may have
shown a second automatic-apply switch, polling and merge timing settings, a
custom name, or status entities. Those options are no longer used.

### Remove

Removing the integration stops future management. It does not automatically
undo the last synchronized device lists.

To return to the settings from before installation:

1. Turn synchronization off.
2. Restore the Home Assistant or platform backups.
3. Check the device list on each target.
4. Remove the integration from **Devices & services**.
5. Delete `/config/custom_components/platform_sync`.
6. Restart Home Assistant.

## Quick setup example

### Goal

Use the Home Assistant home dashboard as the source and synchronize its devices
to Google Home, HomeKit, and Matterbridge.

### Steps

1. Add **Cross-Platform Device Sync**.
2. Select **Enable synchronization**.
3. Choose **Devices on selected Home Assistant dashboard views**.
4. Select the home dashboard view, for example
   `lovelace / default-view`.
5. Select Google Home, HomeKit, and Matterbridge as targets.
6. Enter the Google Assistant device configuration file.
7. Select the managed HomeKit target entries.
8. Enter the Matterbridge endpoint, port, and optional password.
9. Add per-platform additions or exclusions if needed.
10. Review and submit the final page.

After setup:

- A complete check runs after Home Assistant or the integration starts.
- Changes to the selected dashboard views trigger recalculation.
- Nothing is rewritten when no difference is found.
- Changes are synchronized and checked only when needed.

## License

Version 0.6.1 and later are source-available under the
[PolyForm Noncommercial License 1.0.0](../LICENSE). You may inspect, use,
modify, and share the original or modified source for permitted noncommercial
purposes. Commercial use is not licensed. This is a noncommercial
source-available license, not an OSI-approved open source license.

Versions released before 0.6.1 remain under the license included with those
versions.

---

Home Assistant displays **Cross-Platform Device Sync** in English and
**裝置平台同步** in Traditional Chinese. Both languages provide the same
features and setup flow.
