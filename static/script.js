function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("hide");
    document.getElementById("content").classList.toggle("full");
}

function toggleTheme() {
    document.body.classList.toggle("dark-mode");
}

// Loader animation
document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("loader").style.display = "flex";
});

window.addEventListener("load", () => {
    document.getElementById("loader").style.display = "none";
});
// Load saved theme
document.addEventListener("DOMContentLoaded", () => {
    if (localStorage.getItem("theme") === "dark") {
        document.body.classList.add("dark-mode");
    }
});

// Toggle theme + save
function toggleTheme() {
    document.body.classList.toggle("dark-mode");

    if (document.body.classList.contains("dark-mode")) {
        localStorage.setItem("theme", "dark");
    } else {
        localStorage.setItem("theme", "light");
    }
}
