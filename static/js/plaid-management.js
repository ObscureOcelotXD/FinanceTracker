/**
 * Plaid Link + linked institutions table for /plaid page.
 */
(function () {
  function formatTs(iso) {
    if (!iso) {
      return "—";
    }
    try {
      var d = new Date(iso);
      if (Number.isNaN(d.getTime())) {
        return iso;
      }
      return d.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch (_e) {
      return iso;
    }
  }

  function refreshPlaidLinkedTable() {
    var tbody = document.getElementById("plaidLinkedTableBody");
    var empty = document.getElementById("plaidLinkedEmpty");
    var wrap = document.getElementById("plaidLinkedTableWrap");
    if (!tbody || !empty) {
      return;
    }
    fetch("/plaid/items")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var items = data.items || [];
        tbody.innerHTML = "";
        empty.style.display = items.length ? "none" : "block";
        if (wrap) {
          wrap.style.display = items.length ? "block" : "none";
        }
        items.forEach(function (it) {
          var tr = document.createElement("tr");
          var nameTd = document.createElement("td");
          nameTd.textContent = it.institution_name || "—";
          var idTd = document.createElement("td");
          if (it.institution_id) {
            var code = document.createElement("code");
            code.textContent = it.institution_id;
            idTd.appendChild(code);
          } else {
            idTd.textContent = "—";
          }
          var firstTd = document.createElement("td");
          firstTd.className = "text-secondary";
          firstTd.textContent = formatTs(it.first_linked_at_utc);
          var updTd = document.createElement("td");
          updTd.className = "text-secondary";
          updTd.textContent = formatTs(it.updated_at_utc);
          var actTd = document.createElement("td");
          actTd.className = "text-end";
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn btn-sm btn-plaid-disconnect";
          btn.textContent = "Disconnect";
          btn.onclick = function () {
            if (
              !window.confirm(
                "Disconnect this institution? Local Plaid accounts, transactions, and holdings for it will be removed."
              )
            ) {
              return;
            }
            fetch("/plaid/disconnect", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ item_id: it.item_id }),
            })
              .then(function (r) {
                return r.json();
              })
              .then(function (res) {
                if (res.error) {
                  window.alert(res.error);
                  return;
                }
                if (res.warning) {
                  window.alert("Disconnected locally. Note: " + res.warning);
                }
                refreshPlaidLinkedTable();
              })
              .catch(function () {
                window.alert("Disconnect failed.");
              });
          };
          actTd.appendChild(btn);
          tr.appendChild(nameTd);
          tr.appendChild(idTd);
          tr.appendChild(firstTd);
          tr.appendChild(updTd);
          tr.appendChild(actTd);
          tbody.appendChild(tr);
        });
      })
      .catch(function () {
        /* ignore */
      });
  }

  function initPlaidManagement() {
    var linkButton = document.getElementById("linkButton");
    var plaidLinkStatus = document.getElementById("plaidLinkStatus");
    var plaidConsentCheckbox = document.getElementById("plaidConsentCheckbox");

    refreshPlaidLinkedTable();

    if (linkButton && plaidConsentCheckbox) {
      var syncPlaidConnectEnabled = function () {
        linkButton.disabled = !plaidConsentCheckbox.checked;
      };
      syncPlaidConnectEnabled();
      plaidConsentCheckbox.addEventListener("change", syncPlaidConnectEnabled);
    }

    if (linkButton) {
      linkButton.onclick = function () {
        if (plaidLinkStatus) {
          plaidLinkStatus.innerText = "Starting Plaid Link...";
        }
        fetch("/create_link_token", { method: "POST" })
          .then(function (response) {
            return response.json();
          })
          .then(function (data) {
            if (!data.link_token) {
              if (plaidLinkStatus) {
                plaidLinkStatus.innerText =
                  data.error || "Unable to create Plaid Link token.";
              }
              return;
            }

            var handler = window.Plaid.create({
              token: data.link_token,
              onSuccess: function (public_token, metadata) {
                fetch("/exchange_public_token", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    public_token: public_token,
                    institution_name:
                      metadata && metadata.institution
                        ? metadata.institution.name
                        : null,
                    institution_id:
                      metadata && metadata.institution
                        ? metadata.institution.institution_id
                        : null,
                  }),
                })
                  .then(function (response) {
                    return response.json();
                  })
                  .then(function (exchangeData) {
                    if (exchangeData.error) {
                      if (plaidLinkStatus) {
                        plaidLinkStatus.innerText =
                          "Link failed: " + exchangeData.error;
                      }
                      return;
                    }
                    var messages = exchangeData.messages || [];
                    var base =
                      exchangeData.link_action === "updated"
                        ? "Institution reconnected (previous link replaced)."
                        : "Linked successfully.";
                    if (plaidLinkStatus) {
                      if (messages.length) {
                        plaidLinkStatus.innerText =
                          base + " " + messages.join(" ");
                      } else {
                        plaidLinkStatus.innerText = base;
                      }
                    }
                    refreshPlaidLinkedTable();
                  })
                  .catch(function (error) {
                    if (typeof reportClientError === "function") {
                      reportClientError(
                        "plaid_exchange",
                        "Token exchange failed",
                        error && error.message
                      );
                    }
                    if (plaidLinkStatus) {
                      plaidLinkStatus.innerText = "Link failed. Please try again.";
                    }
                  });
              },
              onExit: function (err, _metadata) {
                if (err) {
                  if (typeof reportClientError === "function") {
                    reportClientError(
                      "plaid_link_exit",
                      err.error_message || err.display_message || "exit",
                      err && err.error_code
                    );
                  }
                  if (plaidLinkStatus) {
                    plaidLinkStatus.innerText =
                      err.display_message ||
                      err.error_message ||
                      "Plaid Link exited with an error.";
                  }
                }
              },
            });

            handler.open();
          })
          .catch(function (error) {
            if (typeof reportClientError === "function") {
              reportClientError(
                "plaid_link_token",
                "create_link_token fetch failed",
                error && error.message
              );
            }
            if (plaidLinkStatus) {
              plaidLinkStatus.innerText = "Unable to start Plaid Link.";
            }
          });
      };
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlaidManagement);
  } else {
    initPlaidManagement();
  }
})();
