local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrApplication = import 'LrApplication'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'
local LrView = import 'LrView'
local LrBinding = import 'LrBinding'
local LrFunctionContext = import 'LrFunctionContext'

-- Defaults: use venv Python relative to plugin
local function resolvePythonPath()
    local parent = LrPathUtils.parent(_PLUGIN.path)
    local path = LrPathUtils.child(LrPathUtils.child(parent, '.venv'), 'Scripts/python.exe')
    return LrPathUtils.standardizePath(path)
end

local function resolveScriptPath()
    local parent = LrPathUtils.parent(_PLUGIN.path)
    local path = LrPathUtils.child(parent, 'process.py')
    return LrPathUtils.standardizePath(path)
end

local function ensureCollection(name)
    local catalog = LrApplication.activeCatalog()
    local col = catalog:getChildCollectionByName(name)
    if not col then
        col = catalog:createCollection(name, nil, false)
    end
    return col
end

local function applyResult(photo, rating, label, collectionName)
    local catalog = LrApplication.activeCatalog()
    catalog:withWriteAccessDo("Apply PRO-CULL result", function()
        if rating then photo:setRawMetadata('rating', rating) end
        if label then photo:setRawMetadata('colorNameForLabel', label) end
        if collectionName then
            local col = ensureCollection(collectionName)
            col:addPhotos({ photo })
        end
    end)
end

local function parseTsv(tsvPath)
    local results = {}
    local f = io.open(tsvPath, "r")
    if not f then return results end
    local first = true
    for line in f:lines() do
        if not first then
            local path, q, rating, label, collection, blurry = line:match("([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)")
            if path then
                results[path] = {
                    quality = tonumber(q),
                    rating = tonumber(rating),
                    label = label,
                    collection = collection,
                    blurry = tonumber(blurry) == 1,
                }
            end
        end
        first = false
    end
    f:close()
    return results
end

local function appendLog(line)
    local logPath = LrPathUtils.child(_PLUGIN.path, 'PRO-CULL-log.txt')
    local f = io.open(logPath, 'a')
    if f then
        f:write(os.date('%Y-%m-%d %H:%M:%S') .. ' | ' .. line .. '\n')
        f:close()
    end
end

local function metricsToString(settings)
    local enabled = {}
    if settings.useBlur then table.insert(enabled, 'blur') end
    if settings.useComposition then table.insert(enabled, 'composition') end
    if settings.useLighting then table.insert(enabled, 'lighting') end
    if settings.useNoise then table.insert(enabled, 'noise') end
    if #enabled == 0 then
        return 'none'
    end
    return table.concat(enabled, ',')
end

local function shouldSkipPhoto(photo, settings)
    if settings.skipRatedOrFlagged then
        local rating = photo:getRawMetadata('rating')
        local pickStatus = photo:getRawMetadata('pickStatus')
        if (rating and rating > 0) or (pickStatus and pickStatus ~= 0) then
            return true, 'ratedOrFlagged'
        end
    end
    if settings.skipEdited then
        local hasAdjustments = photo:getRawMetadata('hasDevelopAdjustments')
        if hasAdjustments then
            return true, 'edited'
        end
    end
    return false, nil
end

local function showSettingsDialog()
    local result = nil
    LrFunctionContext.callWithContext("showSettings", function(context)
        local f = LrView.osFactory()
        local props = LrBinding.makePropertyTable(context)
        
        props.useBlur = true
        props.useComposition = true
        props.useLighting = true
        props.useNoise = true
        props.rejectThreshold = 30
        props.reviewThreshold = 65
        props.writeXmp = true
        props.applyToLightroom = true
        props.skipRatedOrFlagged = true
        props.skipEdited = true
        
        local contents = f:column {
            spacing = f:control_spacing(),
            bind_to_object = props,
            
            f:group_box {
                title = "What to analyze",
                fill_horizontal = 1,
                f:row {
                    f:checkbox { title = "Sharpness (blur)", value = LrView.bind('useBlur') },
                    f:checkbox { title = "Composition", value = LrView.bind('useComposition') },
                },
                f:row {
                    f:checkbox { title = "Lighting / exposure", value = LrView.bind('useLighting') },
                    f:checkbox { title = "Noise / grain", value = LrView.bind('useNoise') },
                },
            },
            
            f:group_box {
                title = "Quality score cutoffs (0-100)",
                fill_horizontal = 1,
                f:row {
                    f:static_text { title = "Auto-reject if score is below" },
                    f:edit_field { value = LrView.bind('rejectThreshold'), width_in_digits = 4 },
                },
                f:row {
                    f:static_text { title = "Mark as 'needs review' if score is below" },
                    f:edit_field { value = LrView.bind('reviewThreshold'), width_in_digits = 4 },
                },
                f:static_text {
                    title = "Quality is a 0-100 technical score (sharpness, composition, lighting, noise). Higher is better.",
                    wrap = true,
                },
                f:static_text {
                    title = "Below 'Reject' = likely throwaways; between 'Reject' and 'Review' = on the fence; at or above 'Review' = likely keepers.",
                    wrap = true,
                },
                f:static_text {
                    title = "BETA: These cutoffs are a starting point; please play with them and tell us what feels right.",
                    wrap = true,
                },
            },
            
            f:group_box {
                title = "Skip photos already worked on in Lightroom",
                fill_horizontal = 1,
                f:checkbox {
                    title = "Skip photos that already have a star rating or flag",
                    value = LrView.bind('skipRatedOrFlagged'),
                },
                f:checkbox {
                    title = "Skip photos you've already edited in Develop",
                    value = LrView.bind('skipEdited'),
                },
            },
            
            f:group_box {
                title = "Output",
                fill_horizontal = 1,
                f:checkbox { title = "Write XMP sidecars (recommended)", value = LrView.bind('writeXmp') },
                f:checkbox { title = "Apply ratings/labels to Lightroom catalog", value = LrView.bind('applyToLightroom') },
            },
        }
        
        local dialogResult = LrDialogs.presentModalDialog {
            title = "PRO-CULL Settings (BETA)",
            contents = contents,
            actionVerb = "Run",
        }
        
        if dialogResult == "ok" then
            result = {
                useBlur = props.useBlur,
                useComposition = props.useComposition,
                useLighting = props.useLighting,
                useNoise = props.useNoise,
                rejectThreshold = tonumber(props.rejectThreshold) or 30,
                reviewThreshold = tonumber(props.reviewThreshold) or 65,
                writeXmp = props.writeXmp,
                applyToLightroom = props.applyToLightroom,
                skipRatedOrFlagged = props.skipRatedOrFlagged,
                skipEdited = props.skipEdited,
            }
        end
    end)
    return result
end

local function buildCmdFlags(settings)
    local flags = {}
    
    if settings.useComposition then table.insert(flags, "--composition") end
    if settings.useLighting then table.insert(flags, "--lighting") end
    if settings.useNoise then table.insert(flags, "--noise") end
    
    if settings.writeXmp then
        table.insert(flags, "--write-xmp")
    end
    
    return table.concat(flags, " ")
end

local function runProcessOnPathsWithSettings(paths, tsvPath, settings)
    local quotedPaths = {}
    for _, p in ipairs(paths) do
        table.insert(quotedPaths, string.format('"%s"', p))
    end
    local pythonPath = resolvePythonPath()
    local scriptPath = resolveScriptPath()
    local extraFlags = buildCmdFlags(settings)
    local cmd = string.format('"%s" "%s" -i %s %s --tsv-path "%s"',
        pythonPath, scriptPath, table.concat(quotedPaths, " "), extraFlags, tsvPath)
    appendLog("executing command: " .. cmd)
    local rc = LrTasks.execute(cmd)
    appendLog("command returned: " .. tostring(rc))
    return rc
end

local function main()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if #photos == 0 then
        LrDialogs.message("PRO-CULL (BETA)", "No photos selected.")
        return
    end
    
    local settings = showSettingsDialog()
    if not settings then
        return
    end

    local filteredPhotos = {}
    local skippedRatedOrFlagged = 0
    local skippedEdited = 0

    for _, p in ipairs(photos) do
        local skip, reason = shouldSkipPhoto(p, settings)
        if skip then
            if reason == 'ratedOrFlagged' then
                skippedRatedOrFlagged = skippedRatedOrFlagged + 1
            elseif reason == 'edited' then
                skippedEdited = skippedEdited + 1
            end
        else
            table.insert(filteredPhotos, p)
        end
    end

    if #filteredPhotos == 0 then
        local msg = "All selected photos were skipped based on current filters.\n\n"
        msg = msg .. "Try disabling 'Skip rated/flagged' or 'Skip edited' in PRO-CULL settings."
        LrDialogs.message("PRO-CULL (BETA)", msg)
        appendLog(string.format("mode=settings | total=%d | analyzed=0 | applied=0 | skippedRatedOrFlagged=%d | skippedEdited=%d | status=SKIPPED_ALL", #photos, skippedRatedOrFlagged, skippedEdited))
        return
    end

    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local tsvPath = LrPathUtils.child(tempDir, 'pro_cull_results.tsv')

    local paths = {}
    for _, p in ipairs(filteredPhotos) do
        table.insert(paths, p:getRawMetadata('path'))
    end

    local rc = runProcessOnPathsWithSettings(paths, tsvPath, settings)
    if rc ~= 0 then
        LrDialogs.message("PRO-CULL (BETA)", "Python process failed (code " .. tostring(rc) .. "). Check PRO-CULL-log.txt in the plugin folder.")
        appendLog(string.format("mode=settings | total=%d | analyzed=%d | status=ERROR rc=%d", #photos, #filteredPhotos, rc))
        return
    end

    local applied = 0
    if settings.applyToLightroom then
        local results = parseTsv(tsvPath)
        for _, photo in ipairs(filteredPhotos) do
            local p = photo:getRawMetadata('path')
            local res = results[p]
            if res then
                applyResult(photo, res.rating, res.label, res.collection)
                applied = applied + 1
            end
        end
    end

    local msg = string.format("Analyzed %d of %d selected photos.", #filteredPhotos, #photos)
    if settings.applyToLightroom then
        msg = msg .. string.format(" Applied ratings/labels to %d.", applied)
    end
    if settings.writeXmp then
        msg = msg .. " XMP sidecars written."
    end
    if skippedRatedOrFlagged > 0 or skippedEdited > 0 then
        msg = msg .. string.format(" Skipped: %d rated/flagged, %d edited.", skippedRatedOrFlagged, skippedEdited)
    end
    msg = msg .. "\n\nBETA: Scoring is not final - please experiment with metrics, thresholds, and filters and share feedback."
    LrDialogs.message("PRO-CULL (BETA)", msg)

    local metricsStr = metricsToString(settings)
    appendLog(string.format(
        "mode=settings | total=%d | analyzed=%d | applied=%d | skippedRatedOrFlagged=%d | skippedEdited=%d | metrics=%s | reject<%.1f | review<%.1f | writeXmp=%s | applyToLightroom=%s | status=OK",
        #photos,
        #filteredPhotos,
        applied,
        skippedRatedOrFlagged,
        skippedEdited,
        metricsStr,
        settings.rejectThreshold or 0,
        settings.reviewThreshold or 0,
        tostring(settings.writeXmp),
        tostring(settings.applyToLightroom)
    ))

    LrFileUtils.delete(tsvPath)
end

LrTasks.startAsyncTask(main)
