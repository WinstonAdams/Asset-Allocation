// 最小可掛載版本：供驗證元件掛載、重跑時不重新掛載、selected 回灌。
export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const host = parentElement.querySelector(".city");
  const canvas = parentElement.querySelector(".city-canvas");

  // 只在第一次掛載時賦值；之後重跑若值不變，代表元件沒有被重新掛載。
  if (!host.dataset.mount) {
    host.dataset.mount = String(Date.now());
    canvas.addEventListener("click", () => {
      const next = "tracer-" + Math.floor(Math.random() * 1000);
      setStateValue("selected", next);
    });
  }

  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth || 300;
  canvas.width = width;
  canvas.height = 160;
  ctx.clearRect(0, 0, width, 160);
  ctx.fillStyle = "#888";
  ctx.font = "14px sans-serif";
  ctx.fillText("month=" + data.month + " selected=" + (data.selected || "-"), 12, 24);
  canvas.setAttribute("aria-label", "city tracer");
}
