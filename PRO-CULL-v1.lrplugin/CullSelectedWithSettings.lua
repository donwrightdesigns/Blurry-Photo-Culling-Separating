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
    return LrPathUtils.child(LrPathUtils.child(parent, '.venv'), 'Scripts/python.exe')
end

local function resolveScriptPath()
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
        
        local contents = f:column {
            spacing = f:control_spacing(),
            bind_to_object = props,
            
            f:group_box {
                title = "Metrics to evaluate",
                fill_horizontal = 1,
                f:row {
                    f:checkbox { title = "Blur", value = LrView.bind('useBlur') },
                    f:checkbox { title = "Composition", value = LrView.bind('useComposition') },
                },
                f:row {
                    f:checkbox { title = "Lighting", value = LrView.bind('useLighting') },
                    f:checkbox { title = "Noise", value = LrView.bind('useNoise') },
                },
            },
            
            f:group_box {
                title = "Thresholds (0-100)",
                fill_horizontal = 1,
                f:row {
                    f:static_text { title = "Reject if quality <" },
                    f:edit_field { value = LrView.bind('rejectThreshold'), width_in_digits = 4 },
                },
                f:row {
                    f:static_text { title = "Review if quality <" },
                    f:edit_field { value = LrView.bind('reviewThreshold'), width_in_digits = 4 },
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
            title = "PRO-CULL Settings",
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
    return LrTasks.execute(cmd)
end

local function main()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if #photos == 0 then
        LrDialogs.message("PRO-CULL", "No photos selected.")
        return
    end
    
    local settings = showSettingsDialog()
    if not settings then
        return
    end

    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local tsvPath = LrPathUtils.child(tempDir, 'pro_cull_results.tsv')

    local paths = {}
    for _, p in ipairs(photos) do
        table.insert(paths, p:getRawMetadata('path'))
    end

    local rc = runProcessOnPathsWithSettings(paths, tsvPath, settings)
    if rc ~= 0 then
        LrDialogs.message("PRO-CULL", "Python process failed (code " .. tostring(rc) .. "). Check paths/config.")
        return
    end

    local applied = 0
    if settings.applyToLightroom then
        local results = parseTsv(tsvPath)
        for _, photo in ipairs(photos) do
            local p = photo:getRawMetadata('path')
            local res = results[p]
            if res then
                applyResult(photo, res.rating, res.label, res.collection)
                applied = applied + 1
            end
        end
    end

    local msg = string.format("Processed %d photos.", #photos)
    if settings.applyToLightroom then
        msg = msg .. string.format(" Applied ratings/labels to %d.", applied)
    end
    if settings.writeXmp then
        msg = msg .. " XMP sidecars written."
    end
    LrDialogs.message("PRO-CULL", msg)
    LrFileUtils.delete(tsvPath)
end

LrTasks.startAsyncTask(main)
