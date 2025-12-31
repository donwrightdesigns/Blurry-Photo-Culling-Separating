local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrApplication = import 'LrApplication'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'

-- Use venv Python relative to plugin
local function resolvePythonPath()
    local parent = LrPathUtils.parent(_PLUGIN.path)
    return LrPathUtils.child(LrPathUtils.child(parent, '.venv'), 'Scripts/python.exe')
end

local function resolveScriptPath()
    -- plugin sits inside repo; process.py is one level up
    local parent = LrPathUtils.parent(_PLUGIN.path)
    return LrPathUtils.child(parent, 'process.py')
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
            local path, q, rating, label, collection, blurry = line:match("([^	]+)	([^	]+)	([^	]+)	([^	]+)	([^	]+)	([^	]+)")
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

local function runProcessOnPaths(paths, tsvPath)
    local quotedPaths = {}
    for _, p in ipairs(paths) do
        table.insert(quotedPaths, string.format('"%s"', p))
    end
    local pythonPath = resolvePythonPath()
    local scriptPath = resolveScriptPath()
    local cmd = string.format('"%s" "%s" -i %s --all-metrics --tsv-path "%s"', pythonPath, scriptPath, table.concat(quotedPaths, " "), tsvPath)
    return LrTasks.execute(cmd)
end

local function main()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if #photos == 0 then
        LrDialogs.message("PRO-CULL", "No photos selected.")
        return
    end

    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local tsvPath = LrPathUtils.child(tempDir, 'pro_cull_results.tsv')

    local paths = {}
    for _, p in ipairs(photos) do
        table.insert(paths, p:getRawMetadata('path'))
    end

    LrDialogs.message("PRO-CULL", "Running technical cull on selected photos...")
    local rc = runProcessOnPaths(paths, tsvPath)
    if rc ~= 0 then
        LrDialogs.message("PRO-CULL", "Python process failed (code " .. tostring(rc) .. "). Check paths/config.")
        return
    end

    local results = parseTsv(tsvPath)
    local applied = 0
    for _, photo in ipairs(photos) do
        local p = photo:getRawMetadata('path')
        local res = results[p]
        if res then
            applyResult(photo, res.rating, res.label, res.collection)
            applied = applied + 1
        end
    end

    LrDialogs.message("PRO-CULL", string.format("Applied ratings/labels to %d of %d photos.", applied, #photos))
    LrFileUtils.delete(tsvPath)
end

LrTasks.startAsyncTask(main)
