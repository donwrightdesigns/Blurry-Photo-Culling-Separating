local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrApplication = import 'LrApplication'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'

-- Configure paths
local pythonPath = [[C:\\ProgramData\\miniforge3\\envs\\photo-cull\\python.exe]]
local scriptPath = [[J:\\TOOLS\\ai-photo-cull\\source\\process.py]]

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
    catalog:withWriteAccessDo("Apply PRECURSOR result", function()
        if rating then photo:setRawMetadata('rating', rating) end
        if label then photo:setRawMetadata('colorNameForLabel', label) end
        if collectionName then
            local col = ensureCollection(collectionName)
            col:addPhotos( { photo } )
        end
    end)
end

local function parseTsv(tsvPath)
    local results = {}
    local f = io.open(tsvPath, "r")
    if not f then return results end
    local first = true
    for line in f:lines() do
        if first then first = false goto continue end
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
        ::continue::
    end
    f:close()
    return results
end

local function runProcessOnPaths(paths, tsvPath)
    local quotedPaths = {}
    for _, p in ipairs(paths) do
        table.insert(quotedPaths, string.format('\"%s\"', p))
    end
    local cmd = string.format('\"%s\" \"%s\" -i %s --all-metrics --tsv-path \"%s\"', pythonPath, scriptPath, table.concat(quotedPaths, " "), tsvPath)
    return LrTasks.execute(cmd)
end

local function main()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if #photos == 0 then
        LrDialogs.message("PRECURSOR", "No photos selected.")
        return
    end

    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local tsvPath = LrPathUtils.child(tempDir, 'precursor_results.tsv')

    local paths = {}
    for _, p in ipairs(photos) do
        table.insert(paths, p:getRawMetadata('path'))
    end

    LrDialogs.message("PRECURSOR", "Running technical cull on selected photos...")
    local rc = runProcessOnPaths(paths, tsvPath)
    if rc ~= 0 then
        LrDialogs.message("PRECURSOR", "Python process failed (code " .. tostring(rc) .. "). Check paths/config.")
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

    LrDialogs.message("PRECURSOR", string.format("Applied ratings/labels to %d of %d photos.", applied, #photos))
    LrFileUtils.delete(tsvPath)
end

LrTasks.startAsyncTask(main)
