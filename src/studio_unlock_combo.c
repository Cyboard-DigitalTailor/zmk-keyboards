/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zmk/event_manager.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/matrix_transform.h>
#include <zmk/physical_layouts.h>
#include <zmk/studio/core.h>

LOG_MODULE_REGISTER(studio_unlock_combo, CONFIG_ZMK_STUDIO_LOG_LEVEL);

#define COMBO_NODE DT_COMPAT_GET_ANY_STATUS_OKAY(zmk_studio_unlock_combo)

/* RC()-encoded matrix coordinates: (row << 8) | column */
static const uint32_t combo_keys[] = DT_PROP(COMBO_NODE, keys);

#define NUM_KEYS ARRAY_SIZE(combo_keys)
#define HOLD_MS DT_PROP(COMBO_NODE, hold_time_ms)

BUILD_ASSERT(NUM_KEYS > 0 && NUM_KEYS <= 32, "unlock combo supports 1-32 keys");

/* Key positions of the combo keys in the selected physical layout, or a
 * negative value for keys the active matrix transform does not map. Resolved
 * lazily so we never depend on init ordering against the physical layout
 * subsystem, and re-resolved whenever the selected layout changes.
 */
static int32_t target_positions[NUM_KEYS];
static bool targets_resolved;

static uint32_t held;

static void unlock_work_cb(struct k_work *work) {
    LOG_INF("Unlock combo held for %dms, unlocking", HOLD_MS);
    zmk_studio_core_unlock();
}

static K_WORK_DELAYABLE_DEFINE(unlock_work, unlock_work_cb);

static void reset_tracking(void) {
    held = 0;
    k_work_cancel_delayable(&unlock_work);
}

static int resolve_targets(void) {
    struct zmk_physical_layout const *const *layouts;
    size_t layout_count = zmk_physical_layouts_get_list(&layouts);

    int selected = zmk_physical_layouts_get_selected();
    if (selected < 0 || (size_t)selected >= layout_count) {
        return -ENODEV;
    }

    zmk_matrix_transform_t mt = layouts[selected]->matrix_transform;
    for (size_t i = 0; i < NUM_KEYS; i++) {
        target_positions[i] = zmk_matrix_transform_row_column_to_position(
            mt, combo_keys[i] >> 8, combo_keys[i] & 0xFF);
    }

    targets_resolved = true;
    return 0;
}

static int unlock_combo_listener(const zmk_event_t *eh) {
    if (as_zmk_physical_layout_selection_changed(eh)) {
        targets_resolved = false;
        reset_tracking();
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_position_state_changed *ev = as_zmk_position_state_changed(eh);
    if (!ev) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (!targets_resolved && resolve_targets() < 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    for (size_t i = 0; i < NUM_KEYS; i++) {
        if (target_positions[i] < 0 || (uint32_t)target_positions[i] != ev->position) {
            continue;
        }

        WRITE_BIT(held, i, ev->state);

        if (held == BIT_MASK(NUM_KEYS)) {
            k_work_reschedule(&unlock_work, K_MSEC(HOLD_MS));
        } else {
            k_work_cancel_delayable(&unlock_work);
        }
        break;
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(studio_unlock_combo, unlock_combo_listener);
ZMK_SUBSCRIPTION(studio_unlock_combo, zmk_position_state_changed);
ZMK_SUBSCRIPTION(studio_unlock_combo, zmk_physical_layout_selection_changed);
