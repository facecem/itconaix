/* =====================================================================
   IT conAIX – zentrale Einstellungen
   ---------------------------------------------------------------------
   HIER EINMAL EURE ECHTEN DATEN EINTRAGEN. Sie erscheinen automatisch
   auf der Startseite, im Terminfenster, im Impressum und im Datenschutz.
   Werte in [eckigen Klammern] sind Platzhalter und werden auf der Seite
   gelb markiert, bis sie ersetzt sind.
   Leere Werte ('') blenden die zugehörige Zeile im Impressum aus.
   ===================================================================== */
window.ITC_CONFIG = {
  firma:        'IT conAIX',
  rechtsform:   'GbR',
  inhaber:      'Hezcem Sahin und Halil Doganay',   /* alle Gesellschafter der GbR */
  strasse:      'Alexanderstraße 28',
  plzOrt:       '52062 Aachen',
  telefon:      '',                          /* leer = alle Telefon-Angaben auf der Seite werden ausgeblendet */
  email:        'hallo@itconaix.de',        /* bitte prüfen: existiert diese Adresse? */
  ustId:        '',                          /* z. B. 'DE123456789' – leer lassen, wenn keine vorhanden */
  register:     '',                          /* z. B. 'Amtsgericht Aachen, HRB 12345' – leer bei GbR/Einzelunternehmen */
  verantwortlich: 'Hezcem Sahin, Alexanderstraße 28, 52062 Aachen',  /* inhaltlich Verantwortlicher nach § 18 Abs. 2 MStV */

  /* Online-Terminbuchung (optional):
     leer lassen  -> eigener Kalender, Anfrage geht per E-Mail raus, keine Daten an Dritte.
     Link eintragen (z. B. 'https://cal.com/itconaix/30min') -> echtes Buchungstool,
     wird erst nach Zustimmung im Cookie-Hinweis geladen. */
  bookingUrl:     '',
  bookingAnbieter:'Cal.com',                   /* oder 'Calendly' */
  bookingAnbieterSitz:'Cal.com, Inc., 2261 Market Street #5549, San Francisco, CA 94114, USA'
};

(function(){
  var C=window.ITC_CONFIG, KEY='itconaix-consent';
  var isTodo=function(v){return typeof v==='string'&&/^\[.*\]$|\[/.test(v);};
  var telHref=function(v){return 'tel:'+String(v).replace(/[^\d+]/g,'').replace(/^0/,'+49');};

  /* ---------- Daten in die Seite schreiben ---------- */
  function fill(){
    document.querySelectorAll('[data-cfg]').forEach(function(el){
      var v=C[el.dataset.cfg]; if(v==null)return;
      el.textContent=v; el.classList.toggle('todo',isTodo(v));
    });
    document.querySelectorAll('[data-cfg-mail]').forEach(function(el){el.href='mailto:'+C.email;});
    document.querySelectorAll('[data-cfg-tel]').forEach(function(el){ if(!C.telefon||isTodo(C.telefon)){el.removeAttribute('href');} else el.href=telHref(C.telefon);});
    document.querySelectorAll('[data-cfg-if]').forEach(function(el){el.hidden=!C[el.dataset.cfgIf];});
    document.querySelectorAll('[data-cfg-ifnot]').forEach(function(el){el.hidden=!!C[el.dataset.cfgIfnot];});
  }

  /* ---------- Einwilligung (nur für externe Dienste nötig) ---------- */
  function read(){try{return JSON.parse(localStorage.getItem(KEY));}catch(e){return null;}}
  function write(v){try{localStorage.setItem(KEY,JSON.stringify(v));}catch(e){}}
  var listeners=[];
  var consent={
    get:function(){var s=read();return {extern:!!(s&&s.extern)};},
    set:function(extern){write({v:1,extern:!!extern,ts:new Date().toISOString()});listeners.forEach(function(f){f(consent.get());});},
    decided:function(){return !!read();},
    on:function(f){listeners.push(f);},
    open:function(){openCC(true);}
  };

  var cc=null;
  function buildCC(){
    if(cc)return cc;
    cc=document.createElement('div');
    cc.className='cc';cc.hidden=true;
    cc.setAttribute('role','dialog');cc.setAttribute('aria-labelledby','cc-t');cc.setAttribute('aria-describedby','cc-d');
    var hasExtern=!!C.bookingUrl;
    cc.innerHTML=
      '<h2 id="cc-t">Datenschutz-Einstellungen</h2>'+
      (hasExtern
        ? '<p id="cc-d">Wir verwenden keine Tracking- oder Werbe-Cookies. Für die Online-Terminbuchung können wir '+C.bookingAnbieter+' einbinden. Dabei werden Daten, zum Beispiel eure IP-Adresse, an den Anbieter übertragen, auch in die USA. <a href="datenschutz.html#terminbuchung">Mehr dazu</a></p>'
        : '<p id="cc-d">Diese Website setzt keine Cookies und bindet keine Dienste von Drittanbietern ein. Schriften werden von unserem eigenen Server geladen. <a href="datenschutz.html">Datenschutzerklärung</a></p>')+
      '<div class="cc-opts" '+(hasExtern?'':'hidden')+'>'+
        '<label class="cc-o"><input type="checkbox" checked disabled><span><b>Notwendig</b>Speichert nur diese Auswahl in eurem Browser. Kein Cookie, keine Weitergabe.</span></label>'+
        '<label class="cc-o"><input type="checkbox" id="cc-ext"><span><b>Terminbuchung ('+C.bookingAnbieter+')</b>Lädt den Buchungskalender des Anbieters im Terminfenster.</span></label>'+
      '</div>'+
      '<div class="cc-b">'+
        (hasExtern
          ? '<button type="button" data-cc="none">Nur notwendige</button><button type="button" data-cc="save" class="cc-save" hidden>Auswahl speichern</button><button type="button" data-cc="all">Terminbuchung erlauben</button><button type="button" data-cc="more" class="cc-link">Einstellungen</button>'
          : '<button type="button" data-cc="ok">Verstanden</button>')+
      '</div>';
    document.body.appendChild(cc);
    cc.addEventListener('click',function(e){
      var b=e.target.closest('[data-cc]');if(!b)return;
      var a=b.dataset.cc;
      if(a==='more'){cc.querySelector('.cc-opts').hidden=false;cc.classList.add('cc-wide');b.hidden=true;cc.querySelector('.cc-save').hidden=false;return;}
      if(a==='all')consent.set(true);
      if(a==='none')consent.set(false);
      if(a==='save')consent.set(cc.querySelector('#cc-ext').checked);
      closeCC();
    });
    cc.addEventListener('keydown',function(e){if(e.key==='Escape'&&consent.decided())closeCC();});
    return cc;
  }
  var ccFocus=null;
  function openCC(manual){
    buildCC();
    var ext=cc.querySelector('#cc-ext'); if(ext)ext.checked=consent.get().extern;
    if(manual&&C.bookingUrl){cc.querySelector('.cc-opts').hidden=false;cc.classList.add('cc-wide');var m=cc.querySelector('[data-cc="more"]');if(m)m.hidden=true;cc.querySelector('.cc-save').hidden=false;}
    ccFocus=document.activeElement;cc.hidden=false;
    setTimeout(function(){var f=cc.querySelector('button:not([hidden])');if(f)f.focus();},30);
  }
  function closeCC(){if(!cc)return;cc.hidden=true;if(ccFocus&&ccFocus.focus)ccFocus.focus();}

  window.ITC={config:C,consent:consent,isTodo:isTodo};

  document.addEventListener('DOMContentLoaded',function(){
    fill();
    document.addEventListener('click',function(e){
      if(e.target.closest('[data-cookie-settings]')){e.preventDefault();openCC(true);}
    });
    /* Hinweis nur zeigen, wenn überhaupt ein einwilligungspflichtiger Dienst eingebunden ist */
    if(C.bookingUrl&&!consent.decided())openCC(false);
  });
})();
