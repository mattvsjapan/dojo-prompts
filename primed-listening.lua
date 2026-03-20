-- primed_listening.lua  (2025-06-11)
--
--  n          : toggle Primed Listening on/off (no play/pause side-effects)
--  Cmd+n / Cmd+b (or Meta+n / Meta+b):
--               - Cmd+n  ↑ pause_per_char by 0.01 s
--               - Cmd+b  ↓ pause_per_char by 0.01 s  (min 0.01)
--  SPACE / p   : when playback is paused *by this script* …
--                  • 1st press → cancel auto-resume, keep paused
--                  • 2nd press → resume playback
--  Manual pause by the user (or enabling the script while already paused)
--      enters the same “stand-by / 待機” mode: subs stay visible and
--      the next pause-key press resumes playback.
--
--  pause_per_char is stored in / loaded from:
--      ~/.config/mpv/script-opts/primed_listening.conf
------------------------------------------------------------------

--------------------------- DEFAULTS -----------------------------
local pause_per_char = 0.06     -- seconds paused *per character*
local min_pause      = 0.50     -- never pause for less than this
local min_chars      = 2        -- ignore subs shorter than this
local min_ppc        = 0.01     -- floor for pause_per_char
------------------------------------------------------------------

------------------------ LOAD / SAVE OPTS ------------------------
local conf_name = "primed_listening.conf"

local function conf_path()
    return mp.command_native({ "expand-path", "~~/script-opts/" .. conf_name })
end

local function load_opts()
    local f = io.open(conf_path(), "r")
    if not f then return end
    for line in f:lines() do
        local k, v = line:match("^%s*([%w_]+)%s*=%s*(%S+)")
        if k == "pause_per_char" then
            pause_per_char = tonumber(v) or pause_per_char
        end
    end
    f:close()
end

local function save_opts()
    local f = io.open(conf_path(), "w+")
    if not f then
        mp.msg.error("primed listening: cannot write options file")
        return
    end
    f:write(("pause_per_char=%.4f\n"):format(pause_per_char))
    f:close()
end

load_opts()
------------------------------------------------------------------

--------------------------- STATE -------------------------------
local enabled                = false  -- script master switch
local timer                  = nil    -- auto-resume timer
local awaiting_second_press  = false  -- pause-lock flag
------------------------------------------------------------------

--------------------- UTILITY / HELPERS -------------------------
local pause_keys = { "SPACE", "p", "MBTN_LEFT" }

local function visible_char_count(text)
    if not text or text == "" then return 0 end
    text = text:gsub("{.-}", ""):gsub("\\[Nn]", "")   -- strip ASS
               :gsub("%b()", ""):gsub("（[^）]*）", "")   -- remove (…) （…）
               :gsub("%s+", "")
    local ok, len = pcall(function() return utf8.len(text) end)
    return (ok and len) or #text
end

local function remove_pause_key_bindings()
    for _, key in ipairs(pause_keys) do
        mp.remove_key_binding("pl-first-" .. key)
        mp.remove_key_binding("pl-second-" .. key)
    end
end

local function release_script_control()
    if timer then timer:kill(); timer = nil end
    awaiting_second_press = false
    remove_pause_key_bindings()
end
------------------------------------------------------------------

-- Bindings for the *second* press (resume playback) -------------
local function resume_playback()
    release_script_control()
    mp.set_property_bool("pause", false)
end

local function add_second_press_bindings()
    awaiting_second_press = true
    remove_pause_key_bindings()
    for _, key in ipairs(pause_keys) do
        mp.add_forced_key_binding(key, "pl-second-" .. key, resume_playback)
    end
end
------------------------------------------------------------------

-- First-press handler used when the script paused playback -------
local function lock_pause()
    if timer then timer:kill(); timer = nil end
    mp.osd_message("Pause locked — press again to resume")
    add_second_press_bindings()
end
------------------------------------------------------------------

----------------------- CORE FUNCTION ---------------------------
local function pause_for_current_sub()
    local text  = mp.get_property("sub-text")
    if not text or text == "" then return end

    local chars = visible_char_count(text)
    if chars < min_chars then return end

    local duration = math.max(min_pause, chars * pause_per_char)

    mp.set_property_bool("sub-visibility", true)
    mp.set_property_bool("pause", true)

    timer = mp.add_timeout(duration, resume_playback)
    remove_pause_key_bindings()
    for _, key in ipairs(pause_keys) do
        mp.add_forced_key_binding(key, "pl-first-" .. key, lock_pause)
    end
end
------------------------------------------------------------------

------------------------ OBSERVERS ------------------------------
local function on_sub_text_change(_, new_value)
    if not enabled or awaiting_second_press then return end
    if new_value and new_value ~= "" then pause_for_current_sub() end
end

local function on_pause_change(_, paused)
    if not enabled then return end
    mp.set_property_bool("sub-visibility", paused)

    if paused then
        if not timer and not awaiting_second_press then
            add_second_press_bindings()
        end
    else
        release_script_control()
    end
end
------------------------------------------------------------------

---------------------- TOGGLE HANDLER ---------------------------
local function set_enabled(state)
    if state == enabled then return end
    enabled = state

    release_script_control()

    if enabled then
        local currently_paused = mp.get_property_bool("pause")
        if currently_paused then
            add_second_press_bindings()
            mp.set_property_bool("sub-visibility", true)
        end

        mp.observe_property("sub-text", "string", on_sub_text_change)
        mp.observe_property("pause",    "bool",   on_pause_change)
        mp.osd_message("Primed Listening ENABLED")
    else
        mp.unobserve_property(on_sub_text_change)
        mp.unobserve_property(on_pause_change)
        mp.set_property_bool("sub-visibility", true)
        mp.osd_message("Primed Listening DISABLED")
    end
end
------------------------------------------------------------------

--------------------- PPC DISPLAY / UPDATE ----------------------
local function show_ppc()
    mp.osd_message(("pause_per_char = %.2f s/char"):format(pause_per_char), 1.2)
    save_opts()
end
------------------------------------------------------------------

----------------------- KEY BINDINGS ----------------------------
mp.add_key_binding("n", "toggle-primed-listening", function()
    set_enabled(not enabled)
end)

for _, mod in ipairs({ "CMD", "Meta" }) do
    mp.add_key_binding(mod .. "+n", "increase-ppc-" .. mod, function()
        pause_per_char = pause_per_char + 0.01
        show_ppc()
    end)
    mp.add_key_binding(mod .. "+b", "decrease-ppc-" .. mod, function()
        pause_per_char = math.max(min_ppc, pause_per_char - 0.01)
        show_ppc()
    end)
end
------------------------------------------------------------------
