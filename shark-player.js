/* SHARKTV - único reproductor HTML5 para contenido AllDebrid */
(()=>{
 'use strict';
 const modal=document.getElementById('shark-player-modal');
 const video=document.getElementById('shark-player-video');
 const title=document.getElementById('shark-player-title');
 const closeButton=document.getElementById('shark-player-close');
 const status=document.getElementById('shark-player-status');
 if(!modal||!video||!closeButton)return;

 function cerrarReproductorAllDebrid(){
  video.pause();
  video.removeAttribute('src');
  video.load();
  modal.hidden=true;
  document.body.style.overflow='';
  status.textContent='';
  if(document.fullscreenElement&&document.exitFullscreen){
   document.exitFullscreen().catch(()=>{});
  }
 }
 window.abrirReproductorAllDebrid=(url,nombre='')=>{
  let media;
  try{media=new URL(url,location.href);}catch(e){
   alert('El enlace de reproducción no es válido.');return;
  }
  if(media.protocol!=='https:'&&media.protocol!=='http:'){
   alert('El enlace de reproducción no es válido.');return;
  }
  video.pause();
  video.removeAttribute('src');
  video.load();
  title.textContent=nombre||'SHARKTV';
  status.textContent='Preparando vídeo…';
  modal.hidden=false;
  document.body.style.overflow='hidden';
  video.controls=true;
  video.playsInline=true;
  video.removeAttribute('muted');
  video.defaultMuted=false;
  video.muted=false;
  video.volume=1;
  video.src=media.href;
  video.load();
  const playPromise=video.play();
  if(playPromise&&typeof playPromise.catch==='function'){
   playPromise.catch(()=>{
    status.textContent='Pulsa el botón Activar sonido para iniciar el vídeo con audio.';
   });
  }
 };
 // Un gesto explícito del usuario permite a Chrome iniciar la reproducción con audio
 video.addEventListener('click',()=>{
  if(video.muted||video.volume===0){
   video.removeAttribute('muted');
   video.defaultMuted=false;
   video.muted=false;
   video.volume=1;
  }
  if(video.paused){
   const p=video.play();
   if(p&&p.catch)p.catch(()=>{status.textContent='No se pudo iniciar el vídeo.';});
  }
 });
 video.addEventListener('playing',()=>{status.textContent='';});
 video.addEventListener('volumechange',()=>{
  if(!video.muted&&video.volume>0)status.textContent='';
 });
 video.addEventListener('canplay',()=>{if(video.paused)status.textContent='Pulsa reproducir para comenzar.';});
 video.addEventListener('error',()=>{
  const code=video.error&&video.error.code;
  status.textContent=code===4
   ?'Chrome no admite el formato o códec de este archivo.'
   :'No se ha podido reproducir este vídeo. Comprueba la conexión o el formato.';
 });
 closeButton.addEventListener('click',cerrarReproductorAllDebrid);
 document.addEventListener('keydown',event=>{
  if(modal.hidden)return;
  const key=event.key;
  const code=event.keyCode||event.which;
  if(key==='Escape'||key==='Backspace'||code===4){
   event.preventDefault();
   cerrarReproductorAllDebrid();
  }
 },true);
 window.cerrarReproductorAllDebrid=cerrarReproductorAllDebrid;
})();
