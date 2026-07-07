# Copyright (c) 2026 The ZMK Contributors
# SPDX-License-Identifier: MIT

if(CONFIG_ZMK_STUDIO_UNLOCK_COMBO)
  zephyr_library()
  zephyr_library_sources(src/studio_unlock_combo.c)
  zephyr_include_directories(${APPLICATION_SOURCE_DIR}/include)
endif()
