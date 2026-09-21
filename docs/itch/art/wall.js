// The eight stations, in the order the wall shows them. Counts: data/roster.json.
// "local" = the dataset states no licence for redistribution, so the hosted page
// cannot serve it; it plays in a local copy (ROSTER.md).
const CAST = [
  ["drosophila_female", "Fruit fly", "adult female", "138,639 neurons", "#F2B84B", ""],
  ["drosophila_male", "Fruit fly", "adult male", "166,700 neurons", "#6FB7AE", ""],
  ["zebrafish_larva", "Zebrafish", "larva", "187,052 somas", "#E07A8F", ""],
  ["ciona_larva", "Sea squirt", "larva", "207 neurons", "#A58BE0", ""],
  ["c_elegans_herm", "Roundworm", "hermaphrodite", "302 neurons", "#A8D46F", "local"],
  ["c_elegans_male", "Roundworm", "male", "385 neurons", "#6FA8E0", "local"],
  ["drosophila_larva", "Fruit fly", "larva", "2,952 neurons", "#E0A06F", "local"],
  ["mouse_v1", "Mouse", "visual cortex", "8,221 recorded neurons", "#C9C3B6", "watches"],
];
document.querySelectorAll(".wall").forEach((wall) => {
  wall.innerHTML = CAST.map(([id, name, detail, n, c, tag]) =>
    `<div class="st${tag === "watches" ? " watch" : ""}" style="--c:${c}"><img src="${id}.jpg" alt="">` +
    (tag ? `<em class="tag">${tag === "local" ? "local only" : "watches"}</em>` : "") +
    `<div class="cap"><b><i></i>${name}</b><span><s>${detail}</s><u> · </u>${n}</span></div></div>`).join("");
});
