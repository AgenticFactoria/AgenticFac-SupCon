"""
Async resource cleanup utilities to prevent event loop errors.
"""
import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def cleanup_async_resources(timeout: float = 2.0) -> None:
    """
    Properly clean up async resources including pending tasks and event loop.
    
    Args:
        timeout: Maximum time to wait for tasks to complete (in seconds)
    """
    try:
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread
            return
        
        if not loop or loop.is_closed():
            return
            
        # Get all pending tasks
        try:
            pending_tasks: List[asyncio.Task] = [
                task for task in asyncio.all_tasks(loop) 
                if not task.done()
            ]
            
            if pending_tasks:
                logger.info(f"Cancelling {len(pending_tasks)} pending async tasks...")
                
                # Cancel all pending tasks
                for task in pending_tasks:
                    if not task.cancelled():
                        task.cancel()
                
                # Wait for tasks to complete with timeout
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(
                            asyncio.gather(*pending_tasks, return_exceptions=True),
                            timeout=timeout
                        )
                    )
                    logger.info("All async tasks cleaned up successfully")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for {len(pending_tasks)} tasks to complete")
                except Exception as e:
                    logger.debug(f"Error during task cleanup: {e}")
                    
        except Exception as e:
            logger.debug(f"Error collecting pending tasks: {e}")
        
        # Clean up async generators
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.debug(f"Error during async generator cleanup: {e}")
            
    except Exception as e:
        logger.debug(f"Error during async resource cleanup: {e}")


def safe_async_run(coro, timeout: float = 30.0) -> any:
    """
    Safely run an async coroutine with proper cleanup.
    
    Args:
        coro: The coroutine to run
        timeout: Maximum execution time
        
    Returns:
        The result of the coroutine execution
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
    finally:
        # Ensure proper cleanup
        cleanup_async_resources(timeout=1.0)
        
        # Close the loop
        try:
            if not loop.is_closed():
                loop.close()
        except Exception as e:
            logger.debug(f"Error closing event loop: {e}")


def close_http_client(client, timeout: float = 1.0) -> None:
    """
    Safely close an HTTP client with async cleanup.
    
    Args:
        client: The HTTP client to close (e.g., AsyncOpenAI, httpx.AsyncClient)
        timeout: Maximum time to wait for client close
    """
    if not client:
        return
        
    try:
        if hasattr(client, 'aclose'):
            # httpx.AsyncClient
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    asyncio.wait_for(client.aclose(), timeout=timeout)
                )
            finally:
                cleanup_async_resources(timeout=1.0)
                if not loop.is_closed():
                    loop.close()
                    
        elif hasattr(client, 'close'):
            # Other clients with close method
            client.close()
            
    except Exception as e:
        logger.debug(f"Error closing HTTP client: {e}")