var bookingUrlEl = document.getElementById('booking-url');
if (bookingUrlEl) {
  bookingUrlEl.textContent = window.location.origin + bookingUrlEl.textContent.trim();
}

document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-copy-booking]');
  if (btn) {
    copyLink(btn, document.getElementById('booking-url').textContent.trim());
    return;
  }
  btn = e.target.closest('[data-copy-path]');
  if (btn) {
    copyLink(btn, window.location.origin + btn.dataset.copyPath);
  }
});

function copyLink(btn, url) {
  navigator.clipboard.writeText(url).then(function () {
    var span = btn.querySelector('span');
    span.textContent = 'Copied!';
    setTimeout(function () { span.textContent = 'Copy link'; }, 2000);
  });
}
