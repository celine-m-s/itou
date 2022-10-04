"use strict";

(function() {
  let showConfirm = true;

  function initSlider() {
    const slider = document.getElementById("chosenPercentRange");
    const output = document.getElementById("showChosenPercentValue");
    output.innerHTML = slider.value;

    slider.oninput = function () {
      output.innerHTML = this.value;
    }
  }

  function optOutToggle() {
    const ratioSection = document.getElementById("ratio-select");
    document.getElementById("id_opt_out").addEventListener("change", function (e) {
      ratioSection.classList.toggle("d-none", e.target.checked);
      showConfirm = !e.target.checked;
    })
  }

  function initConfirmModal() {
    document.getElementById("ratio-form").addEventListener("submit", function (e) {
      const text = "Le ratio sélectionné ne sera plus modifiable pour cette campagne de contrôle. Confirmez-vous son enregistrement ?";
      if (showConfirm && !window.confirm(text)) {
        e.preventDefault();
      } else {
        // Clicking cancel in the window.confirm should not lock the submit
        // button.
        e.submitter.disabled = true;
      }
    })
  }

  initSlider();
  optOutToggle();
  initConfirmModal();
})()