document.addEventListener("click", (event) => {
  if (event.target.matches("[data-nav-toggle]")) {
    document.querySelector("[data-nav]")?.classList.toggle("open");
  }
});

const importBox = document.querySelector("[data-ai-import]");
if (importBox) {
  const button = importBox.querySelector("[data-ai-button]");
  const status = importBox.querySelector("[data-ai-status]");
  const fileInput = document.querySelector("#customer-file");
  const supplementalPrompt = document.querySelector("#ai-supplemental-prompt");
  button.addEventListener("click", async () => {
    if (!fileInput.files.length) {
      status.textContent = "请先选择客单文件";
      status.className = "import-status error-text";
      return;
    }
    button.disabled = true;
    status.textContent = "正在读取和识别，请稍候…";
    status.className = "import-status";
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
      status.textContent = "识别完成，已自动填入。请核对后保存。";
      status.className = "import-status success-text";
    } catch (error) {
      status.textContent = error.message;
      status.className = "import-status error-text";
    } finally {
      button.disabled = false;
    }
  });
}

function clearOrderFormForAi(form) {
  form.reset();
  form.querySelectorAll('input[type="file"]').forEach(input => {
    input.value = "";
    input.dispatchEvent(new Event("change", {bubbles: true}));
  });
  form.querySelectorAll("[data-paste-image-status]").forEach(status => {
    status.textContent = "";
    status.className = "paste-image-status";
  });
  form.querySelector("[data-customer-name]")?.dispatchEvent(new Event("input", {bubbles: true}));
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
const orderNumberInput = document.querySelector("[data-order-number]");
const orderDateInput = document.querySelector("[data-order-date]");
const orderPrefixInput = document.querySelector("[data-order-prefix]");
const customerNameInput = document.querySelector("[data-customer-name]");
if (orderNumberInput && orderDateInput && orderPrefixInput && customerNameInput) {
  const customerOptions = [...document.querySelectorAll("#customer-list option")];
  let previewRequest = 0;

  async function refreshOrderNumber() {
    const requestId = ++previewRequest;
    if (!orderPrefixInput.value) {
      orderNumberInput.value = "";
      return;
    }
    const query = new URLSearchParams({
      order_date: orderDateInput.value,
      order_prefix_no: orderPrefixInput.value,
    });
    try {
      const response = await fetch(`/api/next-order-no?${query}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "无法生成订单编号");
      if (requestId === previewRequest) {
        orderNumberInput.value = result.order_no;
        orderNumberInput.setCustomValidity("");
      }
    } catch (error) {
      if (requestId === previewRequest) orderNumberInput.setCustomValidity(error.message);
    }
  }

  function matchCustomer() {
    const selected = customerOptions.find(option => option.value === customerNameInput.value.trim());
    orderPrefixInput.value = selected?.dataset.code || "";
    customerNameInput.setCustomValidity(selected ? "" : "请从客户名称列表中选择匹配客户");
    orderNumberInput.setCustomValidity("");
    refreshOrderNumber();
  }

  customerNameInput.addEventListener("input", matchCustomer);
  customerNameInput.addEventListener("change", matchCustomer);
  orderDateInput.addEventListener("change", refreshOrderNumber);
  if (customerNameInput.value) matchCustomer();
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

    if (process === "印刷/UV") {
      amount += numberValue(row, "plate_fee");
    }
    if (!amountInput) return;
    if (process === "上色" || !process) {
      amountInput.value = "";
      amountInput.placeholder = "手动填写";
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
      processHelp.textContent = "请逐单填写颜色数量；金额暂留空。";
    } else if (process === "印刷/UV") {
      processHelp.textContent = "总金额 =（产品数量 + 备品数量）× 单价 + 版费。";
    } else if (process) {
      processHelp.textContent = "金额 =（产品数量+备品数量）×加工单价。";
    } else {
      processHelp.textContent = "请选择工序，系统会显示对应参数并自动计算金额。";
    }
    rows.querySelectorAll("tr").forEach(recalculateRow);
  }

  function addOutsourceRow(focus = true) {
    rows.appendChild(template.content.cloneNode(true));
    updateProcessUI();
    if (focus) rows.lastElementChild.querySelector("[data-scan-order]").focus();
  }

  outsourceBatch.querySelector("[data-add-outsource-row]").addEventListener("click", () => addOutsourceRow());
  processSelect.addEventListener("change", updateProcessUI);
  outsourceBatch.addEventListener("input", event => {
    if (event.target.matches("[data-manual-amount]")) return;
    const row = event.target.closest("tr");
    if (row) recalculateRow(row);
  });
  outsourceBatch.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-outsource-row]");
    if (!button) return;
    if (rows.children.length === 1) {
      const row = button.closest("tr");
      row.querySelectorAll("input").forEach(input => input.value = input.defaultValue);
      row.querySelectorAll("select").forEach(select => select.selectedIndex = 0);
      recalculateRow(row);
      row.querySelector("[data-scan-order]").focus();
      return;
    }
    button.closest("tr").remove();
  });
  outsourceBatch.addEventListener("keydown", event => {
    if (event.key !== "Enter" || !event.target.matches("[data-scan-order]")) return;
    event.preventDefault();
    if (!event.target.value.trim()) return;
    const next = event.target.closest("tr").nextElementSibling;
    if (next) next.querySelector("[data-scan-order]").focus();
    else addOutsourceRow(true);
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
  updateProcessUI();
  rows.querySelector("[data-scan-order]").focus();
}
document.querySelectorAll("[data-selection-form]").forEach(form => {
  const selectAll = form.querySelector("[data-select-all]");
  const items = [...form.querySelectorAll("[data-select-item]")];
  const count = form.querySelector("[data-selected-count]");
  const actions = [...form.querySelectorAll("[data-requires-selection]")];

  function refreshSelection() {
    const selected = items.filter(item => item.checked).length;
    if (count) count.textContent = String(selected);
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

const contextRows = document.querySelectorAll("[data-context-row], [data-admin-context]");
if (contextRows.length) {
  const menu = document.createElement("div");
  menu.className = "admin-context-menu";
  menu.hidden = true;
  menu.innerHTML = '<button type="button" data-context-edit>修改</button><button type="button" data-context-request>申请修改</button><button type="button" class="danger-button" data-context-delete>删除</button>';
  document.body.appendChild(menu);
  let activeRow = null;

  function closeContextMenu() {
    menu.hidden = true;
    activeRow = null;
  }

  function refreshContextButtons() {
    menu.querySelector("[data-context-edit]").hidden = !activeRow?.dataset.editUrl;
    menu.querySelector("[data-context-request]").hidden = !activeRow?.dataset.requestEditUrl;
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
    const reason = window.prompt(`请输入${activeRow.dataset.recordLabel || "该订单"}的修改原因`);
    if (!reason || !reason.trim()) return;
    const form = document.createElement("form");
    form.method = "post";
    form.action = activeRow.dataset.requestEditUrl;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf";
    csrf.value = activeRow.dataset.csrf || "";
    const reasonInput = document.createElement("input");
    reasonInput.type = "hidden";
    reasonInput.name = "reason";
    reasonInput.value = reason.trim();
    form.append(csrf, reasonInput);
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
