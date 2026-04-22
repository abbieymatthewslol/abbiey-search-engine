(function () {
  function attachSubmitGuard(formId, buttonId) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener(
      "submit",
      function (e) {
        var btn = document.getElementById(buttonId);
        if (btn && (btn.disabled || btn.getAttribute("aria-busy") === "true")) {
          e.preventDefault();
          e.stopImmediatePropagation();
        }
      },
      true
    );
  }
  attachSubmitGuard("sb-signup-form", "signup-submit-sb");
  attachSubmitGuard("signup-form", "signup-submit-legacy");
})();
