/* SHARKTV - reproductor HTML5 AllDebrid con audio activado por defecto */
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
  status.textContent='Preparando vídeo con sonido…';
  modal.hidden=false;
  document.body.style.overflow='hidden';
  video.controls=true;
  video.playsInline=true;
  video.setAttribute('playsinline','');
  video.setAttribute('webkit-playsinline','');
  // No se silencia en ningún momento: audio habilitado y volumen al máximo.
  video.removeAttribute('muted');
  video.defaultMuted=false;
  video.muted=false;
  video.volume=1;
  video.src=media.href;
  video.load();
  const playPromise=video.play();
  if(playPromise&&typeof playPromise.catch==='function'){
   playPromise.catch(()=>{
    // No activar modo silencioso: dejar controles nativos para iniciar con audio.
    status.textContent='Pulsa reproducir en los controles del vídeo para iniciar con sonido.';
   });
  }
 };
 video.addEventListener('playing',()=>{
  status.textContent=(!video.muted&&video.volume>0)?'':'El audio está silenciado por el navegador o el dispositivo.';
 });
 video.addEventListener('volumechange',()=>{
  if(video.muted||video.volume===0){
   status.textContent='El audio está silenciado. Comprueba el volumen del dispositivo y del reproductor.';
  }else{
   status.textContent='';
  }
 });
 video.addEventListener('error',()=>{
  const code=video.error&&video.error.code;
  status.textContent=code===4
   ?'El navegador o WebView no admite el formato de vídeo o alguno de sus códecs de audio/vídeo.'
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