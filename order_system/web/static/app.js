document.addEventListener("click", (event) => {
  if (event.target.matches("[data-nav-toggle]")) {
    document.querySelector("[data-nav]")?.classList.toggle("open");
  }
});

const importBox = document.querySelector("[data-ai-import]");
if (importBox) {
  const button = importBox.querySelector("[data-ai-button]");
  const fileButton = importBox.querySelector("[data-ai-file-button]");
  const status = importBox.querySelector("[data-ai-status]");
  const fileInput = importBox.querySelector("[data-ai-file]");
  const fileName = importBox.querySelector("[data-ai-file-name]");
  const supplementalPrompt = document.querySelector("#ai-supplemental-prompt");
  const allowedOrderImportSuffixes = new Set([
    ".doc", ".docx", ".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".webp"
  ]);
  const suffixByClipboardType = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/csv": "csv",
    "text/html": "html",
    "text/tab-separated-values": "tsv",
  };

  function setImportStatus(message, isError = false, isSuccess = false) {
    status.textContent = message;
    status.className = isError ? "import-status error-text" : isSuccess ? "import-status success-text" : "import-status";
  }

  function refreshImportFileName() {
    fileName.textContent = fileInput.files.length ? fileInput.files[0].name : "未选择文件";
  }

  function setCustomerFile(file) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", {bubbles: true}));
  }

  async function runAiImport() {
    if (!fileInput.files.length) {
      setImportStatus("请先选择客单文件", true);
      return;
    }
    button.disabled = true;
    setImportStatus("正在读取和识别，请稍候…");
    const body = new FormData();
    body.append("file", fileInput.files[0]);
    body.append("supplemental_prompt", supplementalPrompt?.value.trim() || "");
    try {
      const response = await fetch("/api/import-order", {
        method: "POST", body,
        headers: {"X-CSRF-Token": importBox.dataset.csrf}
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "识别失败");
      fillOrderForm(result.data);
      setImportStatus("识别完成，已自动填入。请核对后保存。", false, true);
    } catch (error) {
      setImportStatus(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function orderImportSuffix(file) {
    const name = file.name || "";
    const dotIndex = name.lastIndexOf(".");
    if (dotIndex >= 0) {
      const suffix = name.slice(dotIndex).toLowerCase();
      if (allowedOrderImportSuffixes.has(suffix)) return suffix;
    }
    const typeSuffix = suffixByClipboardType[file.type];
    return typeSuffix ? `.${typeSuffix}` : "";
  }

  function normalizedPastedOrderFile(file) {
    const suffix = orderImportSuffix(file);
    if (!suffix) return null;
    const fallbackName = `pasted-order-${Date.now()}${suffix}`;
    return new File([file], file.name || fallbackName, {type: file.type, lastModified: file.lastModified || Date.now()});
  }

  async function importPastedOrderFile(files) {
    const file = files.map(normalizedPastedOrderFile).find(Boolean);
    if (!file) {
      setImportStatus("请粘贴客单文件", true);
      return;
    }
    setCustomerFile(file);
    await runAiImport();
  }

  function pastedFiles(event) {
    const files = [...(event.clipboardData?.files || [])];
    const itemFiles = [...(event.clipboardData?.items || [])]
      .filter(item => item.kind === "file")
      .map(item => item.getAsFile())
      .filter(Boolean);
    itemFiles.forEach(file => {
      if (!files.some(current => current.name === file.name && current.size === file.size && current.type === file.type)) files.push(file);
    });
    return files;
  }

  fileButton?.addEventListener("click", () => fileInput.click());
  fileInput?.addEventListener("change", refreshImportFileName);
  button.addEventListener("click", runAiImport);
  importBox.addEventListener("paste", event => {
    const files = pastedFiles(event);
    if (!files.length) {
      setImportStatus("请粘贴客单文件", true);
      return;
    }
    event.preventDefault();
    importPastedOrderFile(files);
  });
  refreshImportFileName();
}

function clearOrderFormForAi(form) {
  const customerInput = form.querySelector("[data-customer-name]");
  const selectedCustomer = customerInput?.value || "";
  form.reset();
  if (customerInput && selectedCustomer) customerInput.value = selectedCustomer;
  form.querySelectorAll('input[type="file"]').forEach(input => {
    input.value = "";
    input.dispatchEvent(new Event("change", {bubbles: true}));
  });
  form.querySelectorAll("[data-paste-image-status]").forEach(status => {
    status.textContent = "";
    status.className = "paste-image-status";
  });
  form.querySelectorAll("[data-component-rows]").forEach(rows => {
    rows.innerHTML = "";
  });
  customerInput?.dispatchEvent(new Event("input", {bubbles: true}));
  form.querySelector("[data-order-date]")?.dispatchEvent(new Event("change", {bubbles: true}));
}

function fillOrderForm(data) {
  const form = document.querySelector("#order-form");
  if (!form) return;
  clearOrderFormForAi(form);
  const arrays = new Set(["materials", "plating", "accessories", "polishing", "coloring", "resin", "packaging"]);
  Object.entries(data).forEach(([name, value]) => {
    if (value === null || value === undefined) return;
    if (arrays.has(name) && Array.isArray(value)) {
      if (name === "materials") {
        const bases = new Set();
        const crafts = new Set();
        value.forEach(item => {
          const parts = String(item).split("  ");
          if (parts[0]) bases.add(parts[0]);
          if (parts[1]) crafts.add(parts.slice(1).join("  "));
        });
        form.querySelectorAll('[name="material_base"]').forEach(input => input.checked = bases.has(input.value));
        form.querySelectorAll('[name="material_craft"]').forEach(input => input.checked = crafts.has(input.value));
      } else {
        form.querySelectorAll(`[name="${name}"]`).forEach(input => input.checked = value.includes(input.value));
      }
      return;
    }
    if (name === "size_as_sample") {
      const input = form.querySelector(`[name="${name}"]`);
      if (input) input.checked = Boolean(value);
      return;
    }
    const inputs = form.querySelectorAll(`[name="${name}"]`);
    if (!inputs.length) return;
    if (name === "salesman" && inputs[0].readOnly) return;
    if (inputs[0].type === "radio") {
      inputs.forEach(input => input.checked = input.value === String(value));
    } else {
      inputs[0].value = value;
      inputs[0].dispatchEvent(new Event("change", {bubbles: true}));
    }
  });
}



function refreshImagePreview(fileInput) {
  const preview = fileInput.closest("label")?.querySelector("[data-image-preview]");
  if (!preview) return;
  preview.innerHTML = "";
  [...fileInput.files].forEach((file, index) => {
    const item = document.createElement("span");
    item.className = "image-thumb";
    const image = document.createElement("img");
    image.alt = file.name || "产品图片";
    image.src = URL.createObjectURL(file);
    image.addEventListener("load", () => URL.revokeObjectURL(image.src), {once: true});
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "删除";
    remove.addEventListener("click", () => {
      const transfer = new DataTransfer();
      [...fileInput.files].forEach((current, currentIndex) => {
        if (currentIndex !== index) transfer.items.add(current);
      });
      fileInput.files = transfer.files;
      fileInput.dispatchEvent(new Event("change", {bubbles: true}));
    });
    item.append(image, remove);
    preview.appendChild(item);
  });
}

function bindImagePreviewInput(input) {
  if (!input || input.dataset.previewBound === "1") return;
  input.dataset.previewBound = "1";
  input.addEventListener("change", () => refreshImagePreview(input));
  refreshImagePreview(input);
}

document.querySelectorAll("[data-paste-image-file]").forEach(bindImagePreviewInput);

document.querySelectorAll("[data-remove-existing-image]").forEach(button => {
  button.addEventListener("click", () => {
    const thumb = button.closest(".image-thumb");
    const checkbox = thumb?.querySelector('input[name="existing_images"]');
    if (checkbox) checkbox.checked = false;
    if (thumb) thumb.hidden = true;
  });
});

document.querySelectorAll("[data-component-parts]").forEach(section => {
  const rows = section.querySelector("[data-component-rows]");
  const template = section.querySelector("[data-component-row-template]");
  const addButton = section.querySelector("[data-add-component-part]");
  function bindRow(row) {
    row.querySelectorAll("[data-paste-image-file]").forEach(bindImagePreviewInput);
  }
  function addRow() {
    rows.appendChild(template.content.cloneNode(true));
    bindRow(rows.lastElementChild);
  }
  rows.querySelectorAll(".component-row").forEach(bindRow);
  addButton?.addEventListener("click", addRow);
  section.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-component-part]");
    if (!button) return;
    button.closest(".component-row")?.remove();
  });
});


const pastedImageInputs = document.querySelectorAll("[data-paste-image-target]");
if (pastedImageInputs.length) {
  const allowedImageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  const extensionByType = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"};
  const maxImageSize = 5 * 1024 * 1024;
  const maxImageCount = 6;

  function updatePasteStatus(target, message, isError = false) {
    const status = target.closest("label")?.querySelector("[data-paste-image-status]");
    if (!status) return;
    status.textContent = message;
    status.className = isError ? "paste-image-status error-text" : "paste-image-status";
  }

  pastedImageInputs.forEach(target => {
    const fileInput = document.querySelector(target.dataset.pasteImageTarget);
    if (!fileInput) return;
    target.addEventListener("paste", event => {
      const files = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith("image/"));
      if (!files.length) return;
      event.preventDefault();
      const accepted = [];
      for (const file of files) {
        if (!allowedImageTypes.has(file.type)) {
          updatePasteStatus(target, "仅支持 JPG / PNG / WEBP 图片", true);
          return;
        }
        if (file.size > maxImageSize) {
          updatePasteStatus(target, "单张图片不能超过 5MB", true);
          return;
        }
        accepted.push(file);
      }
      const current = [...fileInput.files];
      if (current.length + accepted.length > maxImageCount) {
        updatePasteStatus(target, "最多上传 6 张产品图片", true);
        return;
      }
      const transfer = new DataTransfer();
      current.forEach(file => transfer.items.add(file));
      accepted.forEach((file, index) => {
        const ext = extensionByType[file.type];
        const name = file.name && file.name !== "image.png" ? file.name : `pasted-${Date.now()}-${index + 1}.${ext}`;
        transfer.items.add(new File([file], name, {type: file.type, lastModified: file.lastModified || Date.now()}));
      });
      fileInput.files = transfer.files;
      fileInput.dispatchEvent(new Event("change", {bubbles: true}));
      updatePasteStatus(target, `已添加 ${accepted.length} 张，当前共 ${fileInput.files.length} 张`);
    });
  });
}

document.querySelectorAll("[data-price-tiers]").forEach(section => {
  const rows = section.querySelector("[data-price-tier-rows]");
  const addButton = section.querySelector("[data-add-price-tier]");
  function addRow(quantity = "", unitPrice = "") {
    const row = document.createElement("tr");
    row.innerHTML = `<td><input type="number" min="0" step="0.0001" name="split_quantity" value="${quantity}"></td><td><input type="number" min="0" step="0.0001" name="split_unit_price" value="${unitPrice}"></td><td><button type="button" data-remove-price-tier>删除</button></td>`;
    rows.appendChild(row);
  }
  addButton?.addEventListener("click", () => addRow());
  section.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-price-tier]");
    if (!button) return;
    const row = button.closest("tr");
    if (rows.children.length <= 1) {
      row.querySelectorAll("input").forEach(input => input.value = "");
    } else {
      row.remove();
    }
  });
});


document.querySelectorAll("[data-workshop-scan]").forEach(section => {
  const rows = section.querySelector("[data-workshop-rows]");
  const template = section.querySelector("[data-workshop-row-template]");
  const addButton = section.querySelector("[data-add-workshop-row]");
  const historyUrl = section.dataset.workshopHistoryUrl || "";
  const historyChecks = new WeakMap();
  const scanAdvanceTimers = new WeakMap();
  const scanStartTimes = new WeakMap();
  const cleanNumber = value => Number(Number(value || 0).toFixed(4)).toString();

  function focusEnd(input) {
    if (!input) return;
    requestAnimationFrame(() => {
      input.scrollLeft = input.scrollWidth;
      if (document.activeElement === input && typeof input.setSelectionRange === "function") {
        const end = input.value.length;
        input.setSelectionRange(end, end);
      }
    });
  }

  async function loadWorkshopHistory(row) {
    const input = row?.querySelector("[data-workshop-order]");
    const orderNo = input?.value.trim() || "";
    if (!row || !historyUrl || !orderNo) {
      if (row) {
        row.dataset.existingWorkshopRecord = "0";
        row.dataset.existingWorkshopOrderNo = "";
      }
      return null;
    }
    if (row.dataset.historyKey === orderNo) return row.dataset.existingWorkshopRecord === "1" ? row.dataset.existingWorkshopOrderNo : null;
    row.dataset.historyKey = orderNo;
    try {
      const response = await fetch(`${historyUrl}?order_no=${encodeURIComponent(orderNo)}`);
      if (!response.ok) throw new Error("history lookup failed");
      const result = await response.json();
      const record = result.record;
      if (!record) {
        row.dataset.existingWorkshopRecord = "0";
        row.dataset.existingWorkshopOrderNo = "";
        return null;
      }
      row.dataset.existingWorkshopRecord = "1";
      row.dataset.existingWorkshopOrderNo = orderNo;
      const priceInput = row.querySelector('[name="unit_price"]');
      if (priceInput) priceInput.value = cleanNumber(record.unit_price);
      const quantityInput = row.querySelector('[name="quantity"]');
      if (quantityInput) quantityInput.value = String(record.quantity || 1);
      return orderNo;
    } catch (error) {
      console.warn("Failed to load workshop history", error);
      row.dataset.existingWorkshopRecord = "0";
      row.dataset.existingWorkshopOrderNo = "";
      return null;
    }
  }

  function scheduleWorkshopHistory(row) {
    if (!row) return;
    clearTimeout(historyChecks.get(row));
    historyChecks.set(row, setTimeout(() => loadWorkshopHistory(row), 200));
  }

  function addRow(focus = true) {
    rows.appendChild(template.content.cloneNode(true));
    const input = rows.lastElementChild.querySelector("[data-workshop-order]");
    if (focus) input.focus();
    focusEnd(input);
  }

  function focusNextWorkshopRow(row) {
    if (!row) return;
    const next = row.nextElementSibling;
    if (next) {
      const input = next.querySelector("[data-workshop-order]");
      input.focus();
      focusEnd(input);
    } else addRow(true);
  }

  function scheduleScanAdvance(input) {
    const row = input.closest("tr");
    if (!row) return;
    const orderNo = input.value.trim();
    if (!orderNo) {
      scanStartTimes.delete(input);
      row.dataset.autoAdvancedFor = "";
      return;
    }
    if (!scanStartTimes.has(input) || orderNo.length <= 1) scanStartTimes.set(input, Date.now());
    clearTimeout(scanAdvanceTimers.get(input));
    scanAdvanceTimers.set(input, setTimeout(() => {
      const current = input.value.trim();
      const elapsed = Date.now() - (scanStartTimes.get(input) || Date.now());
      if (current.length < 8 || row.dataset.autoAdvancedFor === current || elapsed > 1200) return;
      row.dataset.autoAdvancedFor = current;
      loadWorkshopHistory(row);
      focusNextWorkshopRow(row);
    }, 260));
  }

  addButton?.addEventListener("click", () => addRow());
  section.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-workshop-row]");
    if (!button) return;
    const row = button.closest("tr");
    if (rows.children.length <= 1) {
      row.querySelectorAll("input").forEach(input => {
        if (input.name === "unit_price") input.value = "0";
        else if (input.name === "quantity") input.value = "1";
        else input.value = "";
      });
      row.dataset.existingWorkshopRecord = "0";
      row.dataset.existingWorkshopOrderNo = "";
      row.dataset.historyKey = "";
      row.dataset.autoAdvancedFor = "";
      row.querySelector("[data-workshop-order]")?.focus();
    } else row.remove();
  });
  section.addEventListener("input", event => {
    if (!event.target.matches("[data-workshop-order]")) return;
    const row = event.target.closest("tr");
    if (row) {
      row.dataset.historyKey = "";
      row.dataset.existingWorkshopRecord = "0";
      if (row.dataset.autoAdvancedFor && row.dataset.autoAdvancedFor !== event.target.value.trim()) row.dataset.autoAdvancedFor = "";
      focusEnd(event.target);
      scheduleWorkshopHistory(row);
      scheduleScanAdvance(event.target);
    }
  });
  section.addEventListener("change", event => {
    if (!event.target.matches("[data-workshop-order]")) return;
    const row = event.target.closest("tr");
    if (row) loadWorkshopHistory(row);
  });
  section.addEventListener("keydown", event => {
    if (event.key !== "Enter" || !event.target.matches("[data-workshop-order]")) return;
    event.preventDefault();
    if (!event.target.value.trim()) return;
    const row = event.target.closest("tr");
    row.dataset.autoAdvancedFor = event.target.value.trim();
    loadWorkshopHistory(row);
    focusNextWorkshopRow(row);
  });
  section.querySelector("form")?.addEventListener("submit", async event => {
    const submitter = event.submitter || document.activeElement;
    const action = submitter?.getAttribute?.("formaction") || "";
    if (action.endsWith("/ship")) return;
    const activeRows = [...rows.querySelectorAll("tr")].filter(row => row.querySelector("[data-workshop-order]")?.value.trim());
    if (!activeRows.length) return;
    event.preventDefault();
    const duplicates = [];
    for (const row of activeRows) {
      const existingOrderNo = await loadWorkshopHistory(row);
      if (existingOrderNo && !duplicates.includes(existingOrderNo)) duplicates.push(existingOrderNo);
    }
    if (duplicates.length && !window.confirm(`以下订单已在当前车间报到过：${duplicates.join("、")}。是否继续保存新的报到记录？`)) return;
    event.target.submit();
  });
  const first = rows.querySelector("[data-workshop-order]");
  first?.focus();
  focusEnd(first);
});

const orderNumberInput = document.querySelector("[data-order-number]");
const orderDateInput = document.querySelector("[data-order-date]");
const orderPrefixInput = document.querySelector("[data-order-prefix]");
const customerNameInput = document.querySelector("[data-customer-name]");
const refreshOrderNumberButton = document.querySelector("[data-refresh-order-number]");
const manualOrderNumberInput = document.querySelector("[data-manual-order-number]");
if (orderNumberInput && orderDateInput && orderPrefixInput) {
  const customerOptions = customerNameInput ? [...document.querySelectorAll("#customer-list option")] : [];
  let previewRequest = 0;
  let lastAutoKey = "";
  let autoTimer = null;

  function currentOrderKey() {
    return `${orderDateInput.value || ""}|${orderPrefixInput.value || ""}`;
  }

  async function refreshOrderNumber(options = {}) {
    const force = Boolean(options.force);
    if (manualOrderNumberInput?.checked) {
      orderNumberInput.setCustomValidity("");
      return;
    }
    const key = currentOrderKey();
    if (!orderPrefixInput.value) {
      orderNumberInput.value = "";
      lastAutoKey = "";
      return;
    }
    if (!force && orderNumberInput.value.trim() && lastAutoKey === key) return;
    const requestId = ++previewRequest;
    const query = new URLSearchParams({
      order_date: orderDateInput.value,
      order_prefix_no: orderPrefixInput.value,
    });
    if (force) query.set("force", "1");
    try {
      const response = await fetch(`/api/next-order-no?${query}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "无法生成订单编号");
      if (requestId === previewRequest) {
        orderNumberInput.value = result.order_no;
        lastAutoKey = key;
        orderNumberInput.setCustomValidity("");
      }
    } catch (error) {
      if (requestId === previewRequest) orderNumberInput.setCustomValidity(error.message);
    }
  }

  function scheduleAutoOrderNumber() {
    clearTimeout(autoTimer);
    autoTimer = setTimeout(() => refreshOrderNumber(), 120);
  }

  function matchCustomer() {
    const selected = customerOptions.find(option => option.value === customerNameInput.value.trim());
    const nextPrefix = selected?.dataset.code || "";
    const previousKey = currentOrderKey();
    orderPrefixInput.value = nextPrefix;
    customerNameInput.setCustomValidity(selected ? "" : "请从客户名称列表中选择匹配客户");
    orderNumberInput.setCustomValidity("");
    if (currentOrderKey() !== previousKey) orderNumberInput.value = "";
    scheduleAutoOrderNumber();
  }

  if (customerNameInput) {
    customerNameInput.addEventListener("input", matchCustomer);
    customerNameInput.addEventListener("change", matchCustomer);
    orderDateInput.addEventListener("change", () => {
      orderNumberInput.value = "";
      scheduleAutoOrderNumber();
    });
    if (customerNameInput.value) matchCustomer();
  } else {
    orderDateInput.addEventListener("change", () => orderNumberInput.setCustomValidity(""));
  }
  manualOrderNumberInput?.addEventListener("change", () => {
    orderNumberInput.setCustomValidity("");
    refreshOrderNumberButton.disabled = manualOrderNumberInput.checked;
  });
  if (manualOrderNumberInput?.checked && refreshOrderNumberButton) refreshOrderNumberButton.disabled = true;
  refreshOrderNumberButton?.addEventListener("click", () => refreshOrderNumber({force: true}));
}

const outsourceBatch = document.querySelector("[data-outsource-batch]");
if (outsourceBatch) {
  const rows = outsourceBatch.querySelector("[data-outsource-rows]");
  const template = outsourceBatch.querySelector("[data-outsource-row-template]");
  const processSelect = outsourceBatch.querySelector("[data-process-select]");
  const processHelp = outsourceBatch.querySelector("[data-process-help]");
  const factorySelect = outsourceBatch.querySelector("[data-factory-select]");
  const factoryOptions = [...factorySelect.querySelectorAll("option[data-process]")].map(option => ({
    process: option.dataset.process,
    value: option.value,
    label: option.textContent,
  }));
  const orderLookupUrl = outsourceBatch.dataset.orderLookupUrl || "";
  const orderLookupTimers = new WeakMap();
  const duplicateScanTimers = new WeakMap();

  const numberValue = (row, name) => Number(row.querySelector(`[name="${name}"]`)?.value || 0);
  const cleanNumber = (value, digits = 6) => Number(value.toFixed(digits)).toString();

  function recalculateRow(row) {
    const process = processSelect.value;
    const quantity = numberValue(row, "product_quantity") + numberValue(row, "spare_quantity");
    const unitPrice = numberValue(row, "unit_price");
    const materialOutput = row.querySelector("[data-material-price]");
    const amountInput = row.querySelector("[data-manual-amount]");
    let amount = quantity * unitPrice;
    let materialPrice = 0;

    if (process === "冲压") {
      const length = numberValue(row, "length_mm");
      const width = numberValue(row, "width_mm");
      const thickness = numberValue(row, "thickness_mm");
      const density = numberValue(row, "density");
      const weight = numberValue(row, "weight");
      const processingFee = numberValue(row, "processing_fee");
      materialPrice = (length + 3) * (width + 3) * thickness * density * weight;
      amount = quantity * (unitPrice + materialPrice) + processingFee;
      materialOutput.textContent = cleanNumber(materialPrice);
    } else {
      materialOutput.textContent = "-";
    }

    if (process === "上色") {
      amount = quantity * unitPrice * numberValue(row, "color_count");
    } else if (process === "印刷/UV") {
      amount += numberValue(row, "plate_fee");
    }
    if (!amountInput || amountInput.dataset.manualLocked === "1") return;
    if (!process) {
      amountInput.value = "";
      amountInput.placeholder = "自动计算";
    } else {
      amountInput.value = amount.toFixed(2);
      amountInput.placeholder = "自动计算，可修改";
    }
  }

  function updateFactoryOptions() {
    const process = processSelect.value;
    const currentValue = factorySelect.value;
    const seen = new Set();
    const matches = factoryOptions.filter(item => {
      if (item.process !== process || seen.has(item.value)) return false;
      seen.add(item.value);
      return true;
    });
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = !process
      ? "请先选择工序"
      : matches.length ? "请选择加工厂" : "该工艺暂无加工厂";
    const options = matches.map(item => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      return option;
    });
    factorySelect.replaceChildren(placeholder, ...options);
    factorySelect.disabled = !process;
    factorySelect.value = matches.some(item => item.value === currentValue) ? currentValue : "";
  }

  function updateProcessUI() {
    const process = processSelect.value;
    updateFactoryOptions();
    outsourceBatch.querySelectorAll("[data-process-only]").forEach(element => {
      element.hidden = element.dataset.processOnly !== process;
    });
    if (process === "冲压") {
      processHelp.textContent = "材料单价 =（长+3）×（宽+3）×厚度×密度×重量；金额 = 总数量×（加工单价+材料单价）+加工费。";
    } else if (process === "上色") {
      processHelp.textContent = "金额 =（产品数量 + 备品数量）× 加工单价 × 颜色数量。";
    } else if (process === "印刷/UV") {
      processHelp.textContent = "总金额 =（产品数量 + 备品数量）× 单价 + 版费。";
    } else if (process) {
      processHelp.textContent = "金额 =（产品数量+备品数量）×加工单价。";
    } else {
      processHelp.textContent = "请选择工序，系统会显示对应参数并自动计算金额。";
    }
    rows.querySelectorAll("tr").forEach(recalculateRow);
  }

  function showOrderNoEnd(input) {
    if (!input) return;
    requestAnimationFrame(() => {
      input.scrollLeft = input.scrollWidth;
      if (document.activeElement === input && typeof input.setSelectionRange === "function") {
        const end = input.value.length;
        input.setSelectionRange(end, end);
      }
    });
  }

  function addOutsourceRow(focus = true) {
    rows.appendChild(template.content.cloneNode(true));
    updateProcessUI();
    const orderInput = rows.lastElementChild.querySelector("[data-scan-order]");
    showOrderNoEnd(orderInput);
    if (focus) {
      orderInput.focus();
      showOrderNoEnd(orderInput);
    }
  }

  outsourceBatch.querySelector("[data-add-outsource-row]").addEventListener("click", () => addOutsourceRow());
  processSelect.addEventListener("change", () => {
    updateProcessUI();
    rows.querySelectorAll("tr").forEach(checkExistingOutsource);
  });
  async function fillOrderRow(row) {
    const input = row.querySelector("[name=order_no]");
    showOrderNoEnd(input);
    const orderNo = input?.value.trim();
    if (!orderLookupUrl || !orderNo) return;
    if (row.dataset.lastOrderLookup === orderNo && row.dataset.lastOrderFound === "1") return;
    row.dataset.lastOrderLookup = orderNo;
    try {
      const response = await fetch(`${orderLookupUrl}?order_no=${encodeURIComponent(orderNo)}`);
      if (!response.ok) return;
      const result = await response.json();
      const order = result.order;
      row.dataset.lastOrderFound = order ? "1" : "0";
      if (!order) return;
      const businessQuantity = Number(order.quantity || 0);
      const businessSpare = Number(order.spare_quantity || 0);
      const productQuantity = row.querySelector("[name=product_quantity]");
      const outsourceSpare = row.querySelector("[name=spare_quantity]");
      if (productQuantity) productQuantity.value = cleanNumber(businessQuantity + businessSpare);
      if (outsourceSpare && !outsourceSpare.value) outsourceSpare.value = "0";
      const lengthInput = row.querySelector("[name=length_mm]");
      const widthInput = row.querySelector("[name=width_mm]");
      const thicknessInput = row.querySelector("[name=thickness_mm]");
      if (lengthInput && order.width_mm) lengthInput.value = cleanNumber(Number(order.width_mm));
      if (widthInput && order.height_mm) widthInput.value = cleanNumber(Number(order.height_mm));
      if (thicknessInput && order.thickness_mm) thicknessInput.value = cleanNumber(Number(order.thickness_mm));
      recalculateRow(row);
    } catch (error) {
      row.dataset.lastOrderFound = "0";
      console.warn("Failed to look up order", error);
    }
  }

  function scheduleFillOrderRow(row) {
    clearTimeout(orderLookupTimers.get(row));
    orderLookupTimers.set(row, setTimeout(() => fillOrderRow(row), 180));
  }


  function formatHistoryDate(value) {
    if (!value) return "";
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${Number(match[2])}月${Number(match[3])}日` : String(value).slice(0, 10);
  }

  async function checkExistingOutsource(row) {
    const orderNo = row.querySelector("[name=order_no]")?.value.trim();
    const process = processSelect.value;
    const flagType = row.querySelector("[name=flag_type]")?.value || "";
    if (!orderNo || !process || flagType === "remake" || flagType === "replenishment") return;
    const key = `${orderNo}|${process}`;
    if (row.dataset.lastOutsourceHistoryCheck === key) return;
    row.dataset.lastOutsourceHistoryCheck = key;
    try {
      const response = await fetch(`/outsource/history?order_no=${encodeURIComponent(orderNo)}&process_name=${encodeURIComponent(process)}`);
      if (!response.ok) return;
      const result = await response.json();
      const record = result.record;
      if (!record) return;
      const dateText = formatHistoryDate(record.outsource_date || record.created_at);
      window.alert(`${orderNo}订单于${dateText}外发给${record.factory_name || ""}。`);
    } catch (error) {
      console.warn("Failed to check outsource history", error);
    }
  }

  function checkBatchDuplicate(row) {
    const orderNo = row.querySelector("[name=order_no]")?.value.trim();
    const process = processSelect.value;
    const flagType = row.querySelector("[name=flag_type]")?.value || "";
    if (!orderNo || !process || flagType === "remake" || flagType === "replenishment") return false;
    const duplicate = [...rows.querySelectorAll("tr")].find(item => {
      if (item === row) return false;
      const itemOrderNo = item.querySelector("[name=order_no]")?.value.trim();
      const itemFlagType = item.querySelector("[name=flag_type]")?.value || "";
      return itemOrderNo === orderNo && itemFlagType !== "remake" && itemFlagType !== "replenishment";
    });
    const key = `${orderNo}|${process}`;
    if (!duplicate || row.dataset.lastBatchDuplicateAlert === key) return Boolean(duplicate);
    row.dataset.lastBatchDuplicateAlert = key;
    window.alert(`${orderNo}\u8ba2\u5355\u5df2\u5728\u672c\u6b21\u5916\u53d1\u6279\u91cf\u5f55\u5165\u4e2d\u51fa\u73b0\u8fc7\u3002`);
    return true;
  }

  function checkScannedOutsource(row) {
    if (!row) return;
    checkBatchDuplicate(row);
    checkExistingOutsource(row);
  }

  function scheduleOutsourceDuplicateCheck(row) {
    if (!row) return;
    clearTimeout(duplicateScanTimers.get(row));
    duplicateScanTimers.set(row, setTimeout(() => {
      checkScannedOutsource(row);
    }, 250));
  }

  outsourceBatch.addEventListener("input", event => {
    const row = event.target.closest("tr");
    if (!row) return;
    if (event.target.matches("[data-manual-amount]")) {
      event.target.dataset.manualLocked = event.target.value.trim() ? "1" : "";
      if (!event.target.dataset.manualLocked) recalculateRow(row);
      return;
    }
    if (event.target.matches("[name=order_no]")) {
      showOrderNoEnd(event.target);
      scheduleFillOrderRow(row);
      scheduleOutsourceDuplicateCheck(row);
    } else recalculateRow(row);
  });
  outsourceBatch.addEventListener("change", event => {
    if (!event.target.matches("[name=order_no], [name=flag_type]")) return;
    const row = event.target.closest("tr");
    if (row) {
      if (event.target.matches("[name=order_no]")) {
        showOrderNoEnd(event.target);
        fillOrderRow(row);
      }
      checkScannedOutsource(row);
    }
  });
  outsourceBatch.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-outsource-row]");
    if (!button) return;
    if (rows.children.length === 1) {
      const row = button.closest("tr");
      row.querySelectorAll("input").forEach(input => {
        input.value = input.defaultValue;
        delete input.dataset.manualLocked;
      });
      row.querySelectorAll("select").forEach(select => select.selectedIndex = 0);
      recalculateRow(row);
      const orderInput = row.querySelector("[data-scan-order]");
      orderInput.focus();
      showOrderNoEnd(orderInput);
      return;
    }
    button.closest("tr").remove();
  });
  outsourceBatch.addEventListener("keydown", event => {
    if (event.key !== "Enter" || !event.target.matches("[data-scan-order]")) return;
    event.preventDefault();
    if (!event.target.value.trim()) return;
    const row = event.target.closest("tr");
    showOrderNoEnd(event.target);
    fillOrderRow(row);
    checkScannedOutsource(row);
    const next = row.nextElementSibling;
    if (next) {
      const orderInput = next.querySelector("[data-scan-order]");
      orderInput.focus();
      showOrderNoEnd(orderInput);
    } else addOutsourceRow(true);
  });
  outsourceBatch.addEventListener("submit", event => {
    const process = processSelect.value;
    const activeRows = [...rows.querySelectorAll("tr")].filter(row => row.querySelector("[name=order_no]").value.trim());
    if (!activeRows.length) {
      event.preventDefault();
      alert("请至少扫描或输入一个订单号");
      return;
    }
    for (const row of activeRows) {
      const orderNo = row.querySelector("[name=order_no]").value.trim();
      const quantity = numberValue(row, "product_quantity") + numberValue(row, "spare_quantity");
      let message = "";
      if (quantity <= 0) message = `订单 ${orderNo} 的合计数量必须大于 0`;
      if (process === "冲压" && ["length_mm", "width_mm", "thickness_mm", "density", "weight"].some(name => numberValue(row, name) <= 0)) message = `订单 ${orderNo} 必须填写大于 0 的长、宽、厚、密度和重量`;
      if (process === "上色" && numberValue(row, "color_count") <= 0) message = `订单 ${orderNo} 必须填写大于 0 的颜色数量`;
      if (process === "印刷/UV" && !row.querySelector("[name=plate_fee]").value.trim()) message = `订单 ${orderNo} 必须填写版费`;
      if (message) {
        event.preventDefault();
        alert(message);
        return;
      }
    }
  });
  outsourceBatch.addEventListener("focusin", event => {
    if (event.target.matches("[name=order_no]")) showOrderNoEnd(event.target);
  });
  updateProcessUI();
  const firstOrderInput = rows.querySelector("[data-scan-order]");
  firstOrderInput.focus();
  showOrderNoEnd(firstOrderInput);
}

document.querySelectorAll("[data-outsource-receive]").forEach(form => {
  const rows = form.querySelector("[data-receive-rows]");
  const template = form.querySelector("[data-receive-row-template]");
  const addButton = form.querySelector("[data-add-receive-row]");

  function showEnd(input) {
    if (!input) return;
    requestAnimationFrame(() => {
      input.scrollLeft = input.scrollWidth;
      if (document.activeElement === input && typeof input.setSelectionRange === "function") {
        const end = input.value.length;
        input.setSelectionRange(end, end);
      }
    });
  }

  function addRow(focus = true) {
    rows.appendChild(template.content.cloneNode(true));
    const input = rows.lastElementChild.querySelector("[data-receive-order]");
    if (focus) input.focus();
    showEnd(input);
  }

  addButton?.addEventListener("click", () => addRow());
  form.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-receive-row]");
    if (!button) return;
    if (rows.children.length === 1) {
      const input = rows.querySelector("[data-receive-order]");
      input.value = "";
      input.focus();
      showEnd(input);
      return;
    }
    button.closest("tr")?.remove();
  });
  form.addEventListener("keydown", event => {
    if (event.key !== "Enter" || !event.target.matches("[data-receive-order]")) return;
    event.preventDefault();
    if (!event.target.value.trim()) return;
    const row = event.target.closest("tr");
    const next = row.nextElementSibling;
    if (next) {
      const input = next.querySelector("[data-receive-order]");
      input.focus();
      showEnd(input);
    } else addRow(true);
  });
  form.addEventListener("input", event => {
    if (event.target.matches("[data-receive-order]")) showEnd(event.target);
  });
  form.addEventListener("submit", event => {
    const activeRows = [...rows.querySelectorAll("tr")].filter(row => row.querySelector("[data-receive-order]")?.value.trim());
    if (!activeRows.length) {
      event.preventDefault();
      alert("请至少扫描或输入一个订单号");
      return;
    }
    const seen = new Set();
    for (const row of activeRows) {
      const orderNo = row.querySelector("[data-receive-order]").value.trim();
      if (seen.has(orderNo)) {
        event.preventDefault();
        alert(`${orderNo} 已在本次收货批量录入中出现过。`);
        return;
      }
      seen.add(orderNo);
    }
  });
  const first = rows.querySelector("[data-receive-order]");
  showEnd(first);
});

document.querySelectorAll("[data-selection-form]").forEach(form => {
  const selectAll = form.querySelector("[data-select-all]");
  const items = [...form.querySelectorAll("[data-select-item]")];
  const count = form.querySelector("[data-selected-count]");
  const unpaidTotal = form.querySelector("[data-selected-unpaid-total]");
  const actions = [...form.querySelectorAll("[data-requires-selection]")];

  function refreshSelection() {
    const selectedItems = items.filter(item => item.checked);
    const selected = selectedItems.length;
    if (count) count.textContent = String(selected);
    if (unpaidTotal) {
      const total = selectedItems.reduce((sum, item) => sum + Number(item.dataset.unpaidAmount || 0), 0);
      unpaidTotal.textContent = total.toFixed(2);
    }
    actions.forEach(button => button.disabled = selected === 0);
    if (selectAll) {
      selectAll.checked = items.length > 0 && selected === items.length;
      selectAll.indeterminate = selected > 0 && selected < items.length;
    }
  }

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      items.forEach(item => item.checked = selectAll.checked);
      refreshSelection();
    });
  }
  items.forEach(item => item.addEventListener("change", refreshSelection));
  refreshSelection();
});


document.querySelectorAll("[data-finance-stash]").forEach(stash => {
  const key = stash.dataset.storageKey || "twd-finance-stash";
  const list = stash.querySelector("[data-stash-list]");
  const empty = stash.querySelector("[data-stash-empty]");
  const clearButton = stash.querySelector("[data-clear-stash]");
  const pdfButton = stash.querySelector("[data-stash-pdf]");
  const hiddenInputs = stash.querySelector("[data-stash-hidden-inputs]");
  const pdfForm = stash.querySelector("[data-stash-pdf-form]");
  let items = [];

  function load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      items = Array.isArray(parsed)
        ? parsed.filter(item => item && String(item.id || "").trim() && String(item.no || "").trim())
        : [];
    } catch (error) {
      items = [];
    }
  }

  function save() {
    localStorage.setItem(key, JSON.stringify(items));
  }

  function render() {
    list.innerHTML = "";
    hiddenInputs.innerHTML = "";
    items.forEach(item => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "finance-stash-chip";
      chip.dataset.removeStashId = item.id;
      chip.title = "移出暂存区";
      chip.textContent = item.no;
      const remove = document.createElement("span");
      remove.textContent = "×";
      chip.appendChild(remove);
      list.appendChild(chip);

      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "selected_ids";
      input.value = item.id;
      hiddenInputs.appendChild(input);
    });
    const hasItems = items.length > 0;
    empty.hidden = hasItems;
    pdfButton.disabled = !hasItems;
    clearButton.disabled = !hasItems;
  }

  function addItem(id, no) {
    id = String(id || "").trim();
    no = String(no || "").trim();
    if (!id || !no) return;
    if (!items.some(item => item.id === id)) {
      items.push({id, no});
      save();
      render();
    }
  }

  stash.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-stash-id]");
    if (!button) return;
    items = items.filter(item => item.id !== button.dataset.removeStashId);
    save();
    render();
  });
  clearButton?.addEventListener("click", () => {
    items = [];
    save();
    render();
  });
  pdfForm?.addEventListener("submit", event => {
    if (!items.length) {
      event.preventDefault();
      alert("请先暂存至少一张订单");
    }
  });
  document.addEventListener("finance-stash-add", event => {
    addItem(event.detail?.id, event.detail?.no);
  });

  load();
  render();
});

function submitReplenishmentRequest(dataset) {
  if (!dataset?.replenishmentUrl) return;
  const rawQuantity = window.prompt(`\u8bf7\u8f93\u5165${dataset.recordLabel || "\u8be5\u8ba2\u5355"}\u7684\u8865\u6570\u6570\u91cf`);
  if (rawQuantity === null) return;
  const quantity = rawQuantity.trim();
  if (!/^[1-9]\d*$/.test(quantity)) {
    window.alert("\u8865\u6570\u6570\u91cf\u5fc5\u987b\u662f\u5927\u4e8e 0 \u7684\u6574\u6570");
    return;
  }
  const rawReason = window.prompt(`\u8bf7\u8f93\u5165${dataset.recordLabel || "\u8be5\u8ba2\u5355"}\u7684\u8865\u6570\u539f\u56e0`);
  if (!rawReason || !rawReason.trim()) {
    window.alert("\u8bf7\u586b\u5199\u8865\u6570\u539f\u56e0");
    return;
  }
  const form = document.createElement("form");
  form.method = "post";
  form.action = dataset.replenishmentUrl;
  const csrf = document.createElement("input");
  csrf.type = "hidden";
  csrf.name = "csrf";
  csrf.value = dataset.csrf || "";
  const quantityInput = document.createElement("input");
  quantityInput.type = "hidden";
  quantityInput.name = "quantity";
  quantityInput.value = quantity;
  const reasonInput = document.createElement("input");
  reasonInput.type = "hidden";
  reasonInput.name = "reason";
  reasonInput.value = rawReason.trim();
  form.append(csrf, quantityInput, reasonInput);
  document.body.appendChild(form);
  form.submit();
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-inline-replenish]");
  if (!button) return;
  event.preventDefault();
  submitReplenishmentRequest(button.dataset);
});

const contextRows = document.querySelectorAll("[data-context-row], [data-admin-context]");
if (contextRows.length) {
  const menu = document.createElement("div");
  menu.className = "admin-context-menu";
  menu.hidden = true;
  menu.innerHTML = '<button type="button" data-context-edit>修改</button><button type="button" data-context-request>申请修改</button><button type="button" data-context-workshop-quantity>申请改数量</button><button type="button" data-context-stash>暂存</button><button type="button" data-context-replenish>申请补数</button><button type="button" data-context-ship>出货</button><button type="button" class="danger-button" data-context-delete>删除</button>';
  document.body.appendChild(menu);
  let activeRow = null;

  function closeContextMenu() {
    menu.hidden = true;
    activeRow = null;
  }

  function refreshContextButtons() {
    menu.querySelector("[data-context-edit]").hidden = !activeRow?.dataset.editUrl;
    menu.querySelector("[data-context-request]").hidden = !activeRow?.dataset.requestEditUrl;
    menu.querySelector("[data-context-workshop-quantity]").hidden = !activeRow?.dataset.workshopQuantityUrl;
    menu.querySelector("[data-context-stash]").hidden = !activeRow?.dataset.stashId;
    menu.querySelector("[data-context-replenish]").hidden = !activeRow?.dataset.replenishmentUrl;
    const shipButton = menu.querySelector("[data-context-ship]");
    shipButton.hidden = !activeRow?.dataset.shipUrl;
    if (!shipButton.hidden) shipButton.textContent = activeRow.dataset.shipped === "1" ? "撤回出货" : "出货";
    menu.querySelector("[data-context-delete]").hidden = !activeRow?.dataset.deleteUrl;
  }

  contextRows.forEach(row => row.addEventListener("contextmenu", event => {
    event.preventDefault();
    activeRow = row;
    refreshContextButtons();
    menu.hidden = false;
    const left = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
    const top = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
    menu.style.left = `${Math.max(8, left)}px`;
    menu.style.top = `${Math.max(8, top)}px`;
  }));

  menu.querySelector("[data-context-edit]").addEventListener("click", () => {
    if (activeRow?.dataset.editUrl) window.location.href = activeRow.dataset.editUrl;
  });
  menu.querySelector("[data-context-request]").addEventListener("click", () => {
    if (!activeRow?.dataset.requestEditUrl) return;
    window.location.href = activeRow.dataset.requestEditUrl;
  });
  menu.querySelector("[data-context-workshop-quantity]").addEventListener("click", () => {
    if (!activeRow?.dataset.workshopQuantityUrl) return;
    const currentQuantity = activeRow.dataset.workshopQuantity || "1";
    const rawQuantity = window.prompt(`请输入${activeRow.dataset.recordLabel || "该记录"}的新数量`, currentQuantity);
    if (rawQuantity === null) return;
    const quantity = rawQuantity.trim();
    if (!/^[1-9]\d*$/.test(quantity)) {
      window.alert("数量必须是大于 0 的整数");
      return;
    }
    const rawReason = window.prompt(`请输入${activeRow.dataset.recordLabel || "该记录"}的修改原因`);
    if (!rawReason || !rawReason.trim()) {
      window.alert("请填写修改原因");
      return;
    }
    const form = document.createElement("form");
    form.method = "post";
    form.action = activeRow.dataset.workshopQuantityUrl;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf";
    csrf.value = activeRow.dataset.csrf || "";
    const quantityInput = document.createElement("input");
    quantityInput.type = "hidden";
    quantityInput.name = "quantity";
    quantityInput.value = quantity;
    const reasonInput = document.createElement("input");
    reasonInput.type = "hidden";
    reasonInput.name = "reason";
    reasonInput.value = rawReason.trim();
    form.append(csrf, quantityInput, reasonInput);
    document.body.appendChild(form);
    form.submit();
  });
  menu.querySelector("[data-context-stash]").addEventListener("click", () => {
    if (!activeRow?.dataset.stashId) return;
    document.dispatchEvent(new CustomEvent("finance-stash-add", {
      detail: {id: activeRow.dataset.stashId, no: activeRow.dataset.stashNo || activeRow.dataset.recordLabel || ""}
    }));
    closeContextMenu();
  });
  menu.querySelector("[data-context-replenish]").addEventListener("click", () => {
    submitReplenishmentRequest(activeRow?.dataset);
  });
  menu.querySelector("[data-context-ship]").addEventListener("click", () => {
    if (!activeRow?.dataset.shipUrl) return;
    const form = document.createElement("form");
    form.method = "post";
    form.action = activeRow.dataset.shipUrl;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf";
    csrf.value = activeRow.dataset.csrf || "";
    const shipped = document.createElement("input");
    shipped.type = "hidden";
    shipped.name = "shipped";
    shipped.value = activeRow.dataset.shipped === "1" ? "0" : "1";
    form.append(csrf, shipped);
    document.body.appendChild(form);
    form.submit();
  });
  menu.querySelector("[data-context-delete]").addEventListener("click", () => {
    if (!activeRow?.dataset.deleteUrl) return;
    const label = activeRow.dataset.recordLabel || "该记录";
    if (!window.confirm(`确定删除${label}？此操作无法撤销。`)) return;
    const form = document.createElement("form");
    form.method = "post";
    form.action = activeRow.dataset.deleteUrl;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf";
    csrf.value = activeRow.dataset.csrf || "";
    form.appendChild(csrf);
    document.body.appendChild(form);
    form.submit();
  });
  document.addEventListener("click", event => {
    if (!menu.contains(event.target)) closeContextMenu();
  });
  window.addEventListener("blur", closeContextMenu);
  window.addEventListener("scroll", closeContextMenu, true);
}
