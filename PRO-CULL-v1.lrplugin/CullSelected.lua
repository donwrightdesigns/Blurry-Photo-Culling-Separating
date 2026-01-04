local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrApplication = import 'LrApplication'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'

-- Use venv Python relative to plugin
local function resolvePythonPath()
    local parent = LrPathUtils.parent(_PLUGIN.path)
    local path = LrPathUtils.child(LrPathUtils.child(parent, '.venv'), 'Scripts/python.exe')
    return LrPathUtils.standardizePath(path)
end

local function resolveScriptPath()
    -- plugin sits inside repo; process.py is one level up
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

local function shouldSkipPhoto(photo)
    local rating = photo:getRawMetadata('rating')
    local pickStatus = photo:getRawMetadata('pickStatus')
    if (rating and rating > 0) or (pickStatus and pickStatus ~= 0) then
        return true, 'ratedOrFlagged'
    end
    local hasAdjustments = photo:getRawMetadata('hasDevelopAdjustments')
    if hasAdjustments then
        return true, 'edited'
    end
    return false, nil
end

local function runProcessOnPaths(paths, tsvPath)
    local quotedPaths = {}
    for _, p in ipairs(paths) do
        table.insert(quotedPaths, string.format('"%s"', p))
    end
    local pythonPath = resolvePythonPath()
    local scriptPath = resolveScriptPath()
    local cmd = string.format('"%s" "%s" -i %s --all-metrics --tsv-path "%s"', pythonPath, scriptPath, table.concat(quotedPaths, " "), tsvPath)
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

    local targetPhotos = {}
    local skippedRatedOrFlagged = 0
    local skippedEdited = 0

    for _, p in ipairs(photos) do
        local skip, reason = shouldSkipPhoto(p)
        if skip then
            if reason == 'ratedOrFlagged' then
                skippedRatedOrFlagged = skippedRatedOrFlagged + 1
            elseif reason == 'edited' then
                skippedEdited = skippedEdited + 1
            end
        else
            table.insert(targetPhotos, p)
        end
    end

    if #targetPhotos == 0 then
        local msg = "All selected photos were skipped because they already have ratings/flags or develop edits.\n\n"
        msg = msg .. "Use 'PRO-CULL with Settings...' if you want to override these filters."
        LrDialogs.message("PRO-CULL (BETA)", msg)
        appendLog(string.format("mode=quick | total=%d | analyzed=0 | applied=0 | skippedRatedOrFlagged=%d | skippedEdited=%d | status=SKIPPED_ALL", #photos, skippedRatedOrFlagged, skippedEdited))
        return
    end

    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local tsvPath = LrPathUtils.child(tempDir, 'pro_cull_results.tsv')

    local paths = {}
    for _, p in ipairs(targetPhotos) do
        table.insert(paths, p:getRawMetadata('path'))
    end

    LrDialogs.message("PRO-CULL (BETA)", "Running technical cull on selected photos (BETA scoring)...")
    local rc = runProcessOnPaths(paths, tsvPath)
    if rc ~= 0 then
        LrDialogs.message("PRO-CULL (BETA)", "Python process failed (code " .. tostring(rc) .. "). Check PRO-CULL-log.txt in the plugin folder.")
        appendLog(string.format("mode=quick | total=%d | analyzed=%d | status=ERROR rc=%d", #photos, #targetPhotos, rc))
        return
    end

    local results = parseTsv(tsvPath)
    local applied = 0
    for _, photo in ipairs(targetPhotos) do
        local p = photo:getRawMetadata('path')
        local res = results[p]
        if res then
            applyResult(photo, res.rating, res.label, res.collection)
            applied = applied + 1
        end
    end

    local msg = string.format("Analyzed %d of %d selected photos.", #targetPhotos, #photos)
    msg = msg .. string.format(" Applied ratings/labels to %d.", applied)
    if skippedRatedOrFlagged > 0 or skippedEdited > 0 then
        msg = msg .. string.format(" Skipped: %d rated/flagged, %d edited.", skippedRatedOrFlagged, skippedEdited)
    end
    msg = msg .. "\n\nBETA: Scoring is not final - please experiment and share feedback."
    LrDialogs.message("PRO-CULL (BETA)", msg)

    appendLog(string.format(
        "mode=quick | total=%d | analyzed=%d | applied=%d | skippedRatedOrFlagged=%d | skippedEdited=%d | status=OK",
        #photos,
        #targetPhotos,
        applied,
        skippedRatedOrFlagged,
        skippedEdited
    ))

    LrFileUtils.delete(tsvPath)
end

LrTasks.startAsyncTask(main)
